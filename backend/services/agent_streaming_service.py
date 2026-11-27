"""
Streaming agent execution service.

``stream_agent_events`` is the canonical streaming seam: it owns the
astream loop, the retry logic, metrics and cleanup for one agent chat turn,
and yields typed ``AgentStreamEvent`` instances. The setup and
post-processing phases are fully delegated to
``AgentExecutionService._prepare_turn()`` and ``_finalize_turn()``.

``stream_agent_chat`` is a thin SSE presentation of that seam: it renders
each ``AgentStreamEvent`` as a ``format_sse_event`` string for HTTP/SSE
clients (playground, public API, marketplace, scheduled tasks). Any other
transport should consume ``stream_agent_events`` directly rather than parse
SSE text.
"""

import asyncio
import contextlib
import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, AsyncGenerator, Dict, List, Any

import anyio
import anyio.lowlevel
import psycopg.errors
from fastapi import HTTPException
from langchain.agents.middleware import PIIDetectionError
from langchain_core.messages import AIMessage
from langgraph.types import Command
from sqlalchemy.orm import Session

from langgraph.errors import GraphRecursionError
from services.internal_chat.errors import (
    BUSY_MESSAGE, STEP_LIMIT_ERROR_CODE, STEP_LIMIT_MESSAGE, ChatConversationBusyError,
)
from tools.agentTools import create_agent, prepare_agent_config, build_human_message, compute_thread_id
from tools.langsmith_config import (
    apply_tracing_to_config,
    build_tracing_config,
    resolve_langsmith_settings,
)
from tools.streaming_utils import (
    AgentStreamEvent,
    format_sse_event,
    map_stream_event,
    SSE_TOKEN,
    SSE_HITL_INTERRUPT,
)
from services.agent_execution_context import TurnCompletedHook, is_chat_turn, notify_before_model, tracing_kwargs
from services.agent_execution_service import (
    finish_if_agent_unavailable,
    AgentExecutionService,
    RunPausedForApproval,
    _may_be_paused,
    last_ai_message_id,
    pii_blocked_message,
)
from services import hitl_approval_service as approvals
from models.hitl_approval import ApprovalChannel
from tools.middleware.factory import human_in_the_loop_config, redacts_output
from services.agent_metrics_collector import AgentMetricsCollector
from services.agent_metrics_recorder import record_agent_execution
from services.agent_cache_service import (
    CheckpointerCacheService,
    is_missing_tool_output_error,
)
from utils.logger import get_logger
from utils.turn_failure_log import chat_failure_summary, log_turn_failure
from utils.service_lifecycle import ServiceRetiredError, agent_turn_context_kwargs, set_service_call_context

if TYPE_CHECKING:
    from services.internal_chat.resolved_config import ResolvedChatConfig

logger = get_logger(__name__)

_AGENT_EXECUTION_FAILED = "Agent execution failed"

# Max time a chat turn's finalize + completion hook may keep running after the client left.
FINALIZE_GRACE_S = 30.0


class _AgentStreamSerializationError(RuntimeError):
    """Raised internally when an outgoing event payload is not JSON-safe.

    Caught by ``stream_agent_events``'s own exception handling so the turn
    still ends in exactly one terminal ``error`` event with an accurate
    ``error_kind``/``error_code``, instead of being misreported as a
    cancellation by the ``aclosing`` wrapper in ``stream_agent_chat`` (a bare
    ``json.dumps`` failure inside the SSE bridge would otherwise surface
    there as a generic exception during generator teardown).
    """


def _assert_json_serializable(data: dict, *, event_type: str) -> None:
    """Raise :class:`_AgentStreamSerializationError` if ``data`` cannot be
    rendered as the SSE payload :func:`tools.streaming_utils.format_sse_event`
    will eventually build from it.

    Only called for payloads built from values this service does not fully
    control (e.g. ``OutputParser``/tool output passed through verbatim into
    the ``done`` event), so the check runs once per turn, not per token.
    """
    try:
        json.dumps(data, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise _AgentStreamSerializationError(
            f"{event_type} payload is not JSON-serializable: {exc}"
        ) from exc


async def _read_pause(agent_chain, config) -> "approvals.GraphPause | None":
    """The human-in-the-loop interrupt the graph is paused on, or None."""
    try:
        return await approvals.read_pause(agent_chain, config)
    except Exception as exc:
        # Unreadable state falls back to "no interrupt" so the normal recovery path stays reachable.
        logger.warning("Could not read graph state for pending interrupts: %s", exc)
        return None


async def _final_answer_text(agent_chain, config) -> str:
    """Text of the last AI message in the checkpoint (after after_model middlewares ran)."""
    state = await agent_chain.aget_state(config)
    for msg in reversed((state.values or {}).get("messages", [])):
        if isinstance(msg, AIMessage):
            return msg.text
    return ""


async def _final_answer_message_id(agent_chain, config) -> "str | None":
    """Fallback: id of the final AI message at the thread head of the checkpoint, or None.

    Only used when this run's own stream produced no AI message (see ``run_ai_messages`` in
    ``stream_agent_events``): the thread head can already belong to a concurrent turn of the same
    conversation. ``checkpoint_id`` is dropped from a config copy because after a rollback retry
    it pins an older checkpoint. Which message is "final" is decided by ``last_ai_message_id``.
    """
    try:
        head_config = {**config, "configurable": {
            k: v for k, v in config.get("configurable", {}).items() if k != "checkpoint_id"
        }}
        state = await agent_chain.aget_state(head_config)
        return last_ai_message_id(state.values or {}, current_turn_only=True)
    except Exception as exc:
        logger.warning("Could not read the final AI message id from the checkpoint: %s", exc)
        return None


class AgentStreamingService:
    """Service for streaming agent responses via Server-Sent Events."""

    def __init__(self, db: Session = None) -> None:
        self.execution_service = AgentExecutionService()
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def stream_agent_events(
        self,
        agent_id: int,
        message: str,
        file_references: list | None = None,
        search_params: dict | None = None,
        user_context: dict | None = None,
        conversation_id: int | None = None,
        db: Session | None = None,
        channel: ApprovalChannel = ApprovalChannel.PLAYGROUND,
        resume: "approvals.ResumeRequest | None" = None,
        turn_config: "ResolvedChatConfig | None" = None,
        on_turn_completed: "TurnCompletedHook | None" = None,
    ) -> AsyncGenerator[AgentStreamEvent, None]:
        """Run one agent chat turn and yield typed stream events.

        With ``resume`` the turn answers a human-in-the-loop approval (already claimed
        by the caller) instead of sending a new message, and records its outcome.
        When the run pauses, interactive channels get a ``hitl_interrupt`` event with the
        recorded approval followed by ``done`` (``status: "requires_approval"``); other
        channels have the pause rejected on the spot and get an ``error`` event, so the
        conversation is never left paused.

        This is the **canonical streaming seam**: it runs exactly the
        setup, astream loop, retry, metrics and cleanup logic a chat turn
        needs, and yields :class:`~tools.streaming_utils.AgentStreamEvent`
        instances rather than any wire format. ``stream_agent_chat`` is a
        thin presentation-layer bridge over this generator that renders each
        event as an SSE string; any other transport (e.g. the A2A execution
        bridge) can consume this generator directly and never has to parse
        SSE text.

        Event sequence, mirroring ``stream_agent_chat``'s historical SSE
        order:

        1. ``metadata`` — emitted immediately after setup with conversation/agent
           metadata so the client can bind the conversation ID before tokens
           arrive.
        2. ``thinking`` / ``tool_start`` / ``tool_end`` — emitted while the agent
           reasons and calls tools.
        3. ``token`` — one per partial LLM text chunk.
        4. ``done`` — emitted once after the stream finishes, carrying the full
           parsed response, conversation ID, and any generated files in
           ``data``, plus ``structured``, ``parsed_response``, ``files_data``
           and ``conversation_id`` in ``extra`` for non-SSE consumers.
        5. ``error`` — emitted instead of ``done`` if an unhandled exception
           occurs; ``extra["error_code"]`` carries the metrics error code and
           ``extra["error_kind"]`` a stable, small vocabulary (``"connection"``,
           ``"incomplete_turn"``, ``"http"``, ``"serialization"``,
           ``"agent_failure"``, ``"approval"``, ``"pii_blocked"``,
           ``"service_retired"``) a non-SSE
           consumer can switch on.

        Consumer contract:
            - Always iterate this generator through
              ``async with contextlib.aclosing(self.stream_agent_events(...)) as events:``
              (``stream_agent_chat`` does exactly this). Cancel the *task*
              consuming it rather than calling ``aclose()`` from a different
              task while the owning task is still awaiting a value — that
              races the generator's own cleanup with whatever the other task
              is doing and is not a supported usage.
            - This generator commits ``effective_db`` mid-turn before the
              astream loop (to free the sync connection for the duration of
              LLM I/O) but never closes it. The caller still owns opening and
              closing the session it passed in.
            - Exactly one terminal event (``done`` or ``error``) is yielded
              per successful or failed turn; on a cancellation that arrives
              *before* that terminal event (``CancelledError``/
              ``GeneratorExit``), neither is yielded — the generator
              re-raises instead, after recording the turn as ``"Cancelled"``.
              A ``GeneratorExit`` that instead arrives *after* the terminal
              event (e.g. ``contextlib.aclosing``/the consumer's own
              ``aclose()`` tearing down this now-finished generator right
              after reading its ``done``/``error``) is re-raised too, but
              does **not** overwrite the outcome already recorded for that
              event — it is generator teardown, not a mid-turn cancellation.
            - The retry loop (missing-tool-output recovery) never yields a
              ``token`` before deciding whether to retry or fail, so
              ``data["response"]`` on the final ``done`` is always the
              complete, authoritative answer for that turn — consumers do
              not need to reassemble it from intermediate ``token`` events
              themselves if they would rather wait for ``done``.

        Args:
            agent_id: Primary key of the agent to execute.
            message: The user's text message.
            file_references: Pre-resolved file-reference objects as returned by
                ``FileManagementService``.  Each object must expose
                ``filename``, ``content``, ``file_type``, ``file_id``, and
                ``file_path``.
            search_params: Optional silo search parameters forwarded to
                ``create_agent``.
            user_context: Caller context dict (``user_id``, ``app_id``,
                ``email``, …).
            conversation_id: ID of an existing conversation to continue.  When
                ``None`` and the agent has memory enabled a new conversation is
                created automatically.
            db: SQLAlchemy session.  If omitted the instance-level ``self.db``
                is used.
            channel: Where the turn comes from; decides whether a human-approval
                pause can be answered (see ``hitl_approval_service.is_interactive``).
            resume: Claimed approval to answer instead of sending ``message``. Never combined
                with ``turn_config`` (Chat turns cannot pause for approval).
            turn_config: Frozen per-request ``ResolvedChatConfig`` of the flexible App chat.
                Runs the turn on the hidden internal agent with the turn's model/silo/skills/MCP;
                needs ``conversation_id``. The ``metadata`` event then carries ``turn_config``
                (ids/names) and ``done`` carries ``assistant_message_id`` and, if the hook set it,
                ``turn``. ``None`` keeps the exact legacy behaviour and event payloads.
            on_turn_completed: Chat-only hook ``(ctx, result)`` called by ``_finalize_turn`` after
                a completed turn (never on error / pause / cancellation).

        Yields:
            :class:`~tools.streaming_utils.AgentStreamEvent` instances.
        """
        if turn_config is not None and resume is not None:
            # Programming error: resume paths never carry a turn config (chat turns cannot pause).
            raise ValueError("turn_config cannot be combined with an approval resume")
        if turn_config is not None and channel != ApprovalChannel.INTERNAL_CHAT:
            raise ValueError("a chat turn must use ApprovalChannel.INTERNAL_CHAT")
        effective_db = db or self.db
        mcp_client = None
        ctx = None
        sandbox_turn_active = False

        # Metrics: outcome of this turn, recorded once in the finally block.
        event_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        metrics_status, metrics_error_code, metrics_error_message = "SUCCESS", None, None
        metrics_collector = AgentMetricsCollector()
        first_token_at = None
        # Set to True immediately before every terminal (done/error) yield
        # below. A consumer that stops iterating right after receiving that
        # event (e.g. `contextlib.aclosing.__aexit__` -> `aclose()`, which is
        # exactly what every documented consumer -- `stream_agent_chat`, the
        # A2A executor bridge -- does once it has what it needs) throws
        # `GeneratorExit` back into this generator at that very `yield`,
        # which is otherwise indistinguishable from a real mid-turn
        # cancellation to the `except (CancelledError, GeneratorExit)` below.
        # Without this flag, every successful (or already-reported-error)
        # turn would be mis-recorded as `"Cancelled"` purely because of how
        # its own caller closes the generator afterwards.
        terminal_event_yielded = False
        resume_settled = resume is None

        # Who is calling, for the log line of a blocked (retired-service) call. Plain
        # ContextVar set, never reset across a yield.
        set_service_call_context(**agent_turn_context_kwargs(channel, user_context, agent_id))

        try:
            # ----------------------------------------------------------------
            # 1. Setup phase — delegates entirely to AgentExecutionService
            # ----------------------------------------------------------------
            ctx = await self.execution_service._prepare_turn(
                agent_id=agent_id,
                message=message,
                file_references=file_references,
                search_params=search_params,
                user_context=user_context,
                conversation_id=conversation_id,
                db=effective_db,
                turn_config=turn_config,
            )
            # Same rule as the sync path. (Bare test doubles may lack the property; hence the helper.)
            chat_turn = is_chat_turn(ctx)
            # A Chat turn ignores the agent's middlewares (create_agent drops them), so neither
            # human-in-the-loop nor output redaction applies, whatever the shared row says.
            if (
                resume is None
                and effective_db is not None
                and _may_be_paused(ctx)
            ):
                try:
                    expired = approvals.check_conversation_free(effective_db, ctx.conversation.conversation_id)
                except approvals.ApprovalPendingError as exc:
                    metrics_status, metrics_error_code, metrics_error_message = "ERROR", exc.code, str(exc)
                    terminal_event_yielded = True
                    yield AgentStreamEvent(
                        "error", exc.to_dict(), extra={"error_code": exc.code, "error_kind": "approval"}
                    )
                    return
                if expired is not None:
                    await self.execution_service.expire_approval(effective_db, expired.id)
            sandbox_turn_active = self.execution_service._begin_sandbox_turn(
                ctx,
                db=effective_db,
            )
            # Sub-agents built as tools read current_event_id to link their runs to this one.
            ctx.user_context = {**(ctx.user_context or {}), "current_event_id": event_id}

            # ----------------------------------------------------------------
            # 2. Emit early metadata event so the client has conversation_id
            # ----------------------------------------------------------------
            metadata_data = {
                "conversation_id": ctx.effective_conv_id,
                "session_id": (
                    getattr(ctx.conversation, "session_id", None)
                    if getattr(ctx, "conversation", None)
                    else None
                ),
                "agent_id": agent_id,
                "agent_name": ctx.agent.name,
                "has_memory": ctx.agent.has_memory,
            }
            if chat_turn:
                # The Chat runs on a hidden shared agent: its ids, name and the thread's session id stay server-side.
                for internal_key in ("session_id", "agent_id", "agent_name"):
                    metadata_data.pop(internal_key)
                metadata_data["turn_config"] = turn_config.to_client_summary()
            yield AgentStreamEvent("metadata", metadata_data)

            # ----------------------------------------------------------------
            # 3a. Resolve this session's temporary playground silos (uploaded
            #     media/document retrieval). Computed once here — it does not
            #     change across the streaming retry loop below — and threaded
            #     into create_agent() alongside the sandbox handles.
            # ----------------------------------------------------------------
            temp_silo_ids = None
            session_id_for_media = (
                getattr(ctx.conversation, "session_id", None)
                if getattr(ctx, "conversation", None)
                else None
            )
            if session_id_for_media and effective_db:
                try:
                    from services.playground_media_service import PlaygroundMediaService
                    media_app_id = user_context.get("app_id") if user_context else None
                    if media_app_id:
                        temp_silo_ids = PlaygroundMediaService.get_temp_silo_ids_for_agent(
                            media_app_id, agent_id, session_id_for_media, effective_db
                        )
                except Exception as e:
                    logger.warning("Could not resolve temp playground silos: %s", e)

            accumulated_content = ""
            structured_response = None
            rollback_checkpoint_id = None

            for attempt in range(2):
                mcp_client = None
                # ------------------------------------------------------------
                # 3. Build agent chain
                # ------------------------------------------------------------
                create_agent_result = await create_agent(
                    ctx.fresh_agent,
                    ctx.search_params,
                    ctx.session_id_for_cache,
                    ctx.user_context,
                    ctx.working_dir,
                    sandbox_handle=ctx.sandbox_handle,
                    sandbox_provider=ctx.sandbox_provider,
                    sandbox_session_key=ctx.sandbox_session_key,
                    attached_files=ctx.processed_files,
                    temp_silo_ids=temp_silo_ids or None,
                    user_message=message,
                    turn_config=turn_config,
                )
                agent_chain, mcp_client = create_agent_result[:2]

                config = prepare_agent_config(ctx.fresh_agent, chat_turn=turn_config is not None)
                config["configurable"]["thread_id"] = compute_thread_id(
                    ctx.fresh_agent, ctx.session_id_for_cache, require_session=chat_turn
                )

                if ctx.fresh_agent.has_memory and ctx.session_id_for_cache:
                    logger.info(
                        "Using session-aware thread_id: %s",
                        config["configurable"]["thread_id"],
                    )

                config["configurable"]["question"] = ctx.enhanced_message
                if rollback_checkpoint_id is not None:
                    config["configurable"]["checkpoint_id"] = rollback_checkpoint_id
                config.setdefault("callbacks", []).append(metrics_collector)

                # ------------------------------------------------------------
                # 4. Build the HumanMessage payload (handles multimodal images)
                # ------------------------------------------------------------
                if resume is None:
                    stream_input = {"messages": [build_human_message(
                        ctx.fresh_agent, ctx.enhanced_message, ctx.image_files, ctx.user_context,
                        chat_turn=turn_config is not None,
                    )]}
                else:
                    pause = await _read_pause(agent_chain, config)
                    if pause is None or pause.interrupt_id != resume.approval.interrupt_id:
                        approvals.finish(
                            effective_db, resume.approval.id, approvals.ApprovalStatus.CANCELLED, reason="stale"
                        )
                        resume_settled = True
                        exc = approvals.ApprovalStaleError(
                            "This approval request no longer matches the conversation; it was not applied."
                        )
                        metrics_status, metrics_error_code, metrics_error_message = "ERROR", exc.code, str(exc)
                        terminal_event_yielded = True
                        yield AgentStreamEvent(
                            "error", exc.to_dict(), extra={"error_code": exc.code, "error_kind": "approval"}
                        )
                        return
                    stream_input = Command(resume={"decisions": resume.decisions})

                # ------------------------------------------------------------
                # 5. Attach LangSmith tracer + metadata when configured
                # ------------------------------------------------------------
                ls_settings = resolve_langsmith_settings(getattr(ctx.fresh_agent, "app", None))
                if ls_settings:
                    tracer, overrides = build_tracing_config(
                        ls_settings,
                        agent=ctx.fresh_agent,
                        user_context=ctx.user_context,
                        conversation_id=ctx.effective_conv_id,
                        session_id=ctx.session_id_for_cache,
                        **tracing_kwargs(turn_config),
                    )
                    apply_tracing_to_config(config, tracer, overrides)
                    logger.info(
                        "LangSmith tracing ENABLED — project='%s' source='%s'",
                        ls_settings.project_name,
                        ls_settings.source,
                    )

                # ------------------------------------------------------------
                # 6. Streaming loop — the only part that stays in this service
                # ------------------------------------------------------------
                # Return the sync connection to the pool for the duration of the
                # stream: astream uses the async checkpointer, not this session, so
                # holding it across LLM I/O would exhaust the pool. ctx objects expire
                # but stay attached, so _finalize_turn reloads them on demand.
                notify_before_model(turn_config)  # Chat: renew the busy marker (committed just below)
                if effective_db is not None:
                    effective_db.commit()

                accumulated_content = ""
                structured_response = None
                # PIIMiddleware(apply_to_output) redacts the AI message in after_model, i.e.
                # after its tokens were streamed; hold tokens back so PII never reaches the UI.
                # Neither applies to a chat turn (create_agent drops the agent's middlewares).
                buffer_output = not chat_turn and redacts_output(ctx.fresh_agent)
                hitl_enabled = not chat_turn and human_in_the_loop_config(ctx.fresh_agent) is not None
                run_ai_messages: list = []  # AI messages THIS run produced (chat turns: final id)

                try:
                    # ``aclosing`` guarantees the LangGraph astream generator
                    # itself is closed (releasing the LLM/tool/checkpointer
                    # work it is suspended on) whenever we leave this block
                    # for any reason — normal completion, the retry
                    # ``continue``/``raise`` below, or the consumer cancelling
                    # us mid-token. Without it, a cancelled turn left that
                    # generator suspended until the asyncgen GC hook ran, so
                    # in-flight LLM/tool/checkpointer work kept running after
                    # the turn was already recorded as "Cancelled".
                    async with contextlib.aclosing(
                        agent_chain.astream(
                            stream_input,
                            config=config,
                            stream_mode=["messages", "updates", "custom"],
                        )
                    ) as stream:
                        async for mode, chunk in stream:

                            if mode == "updates":
                                if (
                                    isinstance(chunk, dict)
                                    and "model" in chunk
                                    and isinstance(chunk["model"], dict)
                                    and "structured_response" in chunk["model"]
                                ):
                                    structured_response = chunk["model"]["structured_response"]
                                if isinstance(chunk, dict):
                                    # Only the model node's own output: other nodes (e.g.
                                    # summarization) re-emit preserved messages of earlier turns.
                                    node_update = chunk.get("model")
                                    new_messages = node_update.get("messages") if isinstance(node_update, dict) else None
                                    for message in new_messages if isinstance(new_messages, list) else ():
                                        if not isinstance(message, AIMessage):
                                            continue
                                        if chat_turn:
                                            run_ai_messages.append(message)
                                        # Token events carry text only: images the model generated would be lost.
                                        self.execution_service.save_generated_images(message.content, ctx.working_dir)

                            events = map_stream_event(mode, chunk)
                            if events:
                                for event in events:
                                    if event["type"] == SSE_TOKEN:
                                        if first_token_at is None:
                                            first_token_at = datetime.utcnow()
                                        accumulated_content += event["data"].get("content", "")
                                        if buffer_output:
                                            # Raw tokens are not PII-redacted yet; send the
                                            # redacted final message instead (see below).
                                            continue
                                    yield AgentStreamEvent(event["type"], event["data"])
                    break
                except Exception as stream_exc:
                    if (
                        attempt == 0
                        and ctx.fresh_agent.has_memory
                        and ctx.session_id_for_cache
                        and is_missing_tool_output_error(stream_exc)
                        # A HITL pause leaves the same unanswered tool_call a corrupt
                        # checkpoint does. Deleting it would silently discard the
                        # pending approval and the whole thread's memory.
                        and resume is None
                        and not (hitl_enabled and await _read_pause(agent_chain, config))
                    ):
                        # Recover by forking from the last known-good checkpoint
                        # instead of deleting the whole thread — see the mirrored
                        # fix in AgentExecutionService's non-streaming path for
                        # the full rationale (adelete_thread wipes the user's
                        # entire visible history, not just the broken step).
                        rollback_checkpoint_id = await CheckpointerCacheService.get_rollback_checkpoint_id(
                            ctx.fresh_agent.agent_id,
                            ctx.session_id_for_cache,
                        )
                        if rollback_checkpoint_id is None:
                            logger.warning(
                                "Incomplete tool-call checkpoint for agent %s session %s "
                                "has no earlier checkpoint to roll back to; failing the "
                                "turn instead of retrying",
                                ctx.fresh_agent.agent_id,
                                ctx.session_id_for_cache,
                            )
                            metrics_status = "ERROR"
                            metrics_error_code = type(stream_exc).__name__
                            metrics_error_message = (
                                chat_failure_summary(stream_exc) if turn_config is not None else str(stream_exc)[:2000]
                            )
                            terminal_event_yielded = True
                            yield AgentStreamEvent(
                                "error",
                                {"message": "Your last message could not be completed. Please resend it."},
                                extra={
                                    "error_code": metrics_error_code,
                                    "error_kind": "incomplete_turn",
                                },
                            )
                            return
                        logger.warning(
                            "Detected incomplete tool-call checkpoint for agent %s "
                            "session %s; retrying turn from prior checkpoint %s "
                            "(no history deleted)",
                            ctx.fresh_agent.agent_id,
                            ctx.session_id_for_cache,
                            rollback_checkpoint_id,
                        )
                        continue
                    raise

            raw_response = (
                structured_response
                if structured_response is not None
                else accumulated_content
            )
            if resume is not None:
                approvals.finish(
                    effective_db, resume.approval.id, resume.final_status,
                    reason=resume.reason, decisions=resume.decisions, decided_by=resume.decided_by,
                )
                resume_settled = True

            # A chat turn still looks: an interrupt must never be finalized as a completed turn.
            pause = await _read_pause(agent_chain, config) if (hitl_enabled or chat_turn) else None
            if pause is not None:
                # Paused by HumanInTheLoopMiddleware: nothing to finalize until someone answers.
                requester = approvals.Requester.from_user_context(ctx.user_context)
                answerable = not chat_turn and approvals.is_interactive(channel) and (
                    requester.user_id is not None or bool(requester.api_key_hash)
                )
                approval = await approvals.open_approval(
                    effective_db,
                    agent_chain=agent_chain,
                    config=config,
                    conversation_id=ctx.conversation.conversation_id,
                    agent_id=agent_id,
                    app_id=ctx.fresh_agent.app_id,
                    channel=channel,
                    requester=requester,
                    hitl_config=human_in_the_loop_config(ctx.fresh_agent),
                    answerable=answerable,
                )
                if answerable:
                    yield AgentStreamEvent(SSE_HITL_INTERRUPT, approvals.sse_payload(approval))
                    terminal_event_yielded = True
                    yield AgentStreamEvent(
                        "done",
                        {
                            "response": "",
                            "conversation_id": ctx.effective_conv_id,
                            "files": [],
                            "hitl_paused": True,
                            "status": "requires_approval",
                            "approval_id": approval.id,
                        },
                        extra={"conversation_id": ctx.effective_conv_id, "approval_id": approval.id},
                    )
                    return
                await self.execution_service._reject_in_place(
                    RunPausedForApproval(agent_chain, config), approval, effective_db
                )
                tools = ", ".join(a["name"] for a in approval.actions)
                exc = approvals.ApprovalNotSupportedError(
                    f"This agent needs human approval before running {tools}, which this chat cannot provide. "
                    "The tool was not executed.",
                    approval_id=approval.id,
                )
                metrics_status, metrics_error_code, metrics_error_message = "ERROR", exc.code, str(exc)
                terminal_event_yielded = True
                yield AgentStreamEvent(
                    "error", exc.to_dict(), extra={"error_code": exc.code, "error_kind": "approval"}
                )
                return

            if buffer_output and structured_response is None:
                raw_response = await _final_answer_text(agent_chain, config)

            # ----------------------------------------------------------------
            # 7. Post-processing phase — delegates to AgentExecutionService
            # ----------------------------------------------------------------

            finalize_kwargs: dict = {}
            if chat_turn:
                assistant_message_id = last_ai_message_id({"messages": run_ai_messages})
                if assistant_message_id is None:
                    assistant_message_id = await _final_answer_message_id(agent_chain, config)
                if assistant_message_id is None:
                    logger.warning(
                        "Chat turn finished without a readable assistant message id (conversation %s)",
                        ctx.effective_conv_id,
                    )
                finalize_kwargs = {
                    "assistant_message_id": assistant_message_id,
                    "on_turn_completed": on_turn_completed,
                }
            result = await self._finalize(ctx, raw_response, effective_db, chat_turn, finalize_kwargs)

            # ----------------------------------------------------------------
            # 8. Emit done event
            # ----------------------------------------------------------------
            done_data = {
                "response": result["parsed_response"],
                "conversation_id": result["effective_conv_id"],
                "files": result["files_data"],
                "status": "completed",
            }
            skipped_outputs = (result.get("metadata") or {}).get("outputs_skipped")
            if skipped_outputs:  # agents only (absent for the Chat, which uses a turn warning)
                done_data["outputs_skipped"] = skipped_outputs
            if chat_turn:
                done_data["assistant_message_id"] = result.get("assistant_message_id")
                done_data["turn"] = result.get("turn")
            # Validate up front rather than let format_sse_event's json.dumps
            # raise inside the SSE bridge: a failure there would surface
            # through contextlib.aclosing's teardown of this generator and
            # get misreported as a cancellation instead of a real error, and
            # no SSE error event would ever reach the client.
            _assert_json_serializable(done_data, event_type="done")
            terminal_event_yielded = True
            yield AgentStreamEvent(
                "done",
                done_data,
                extra={
                    "structured": structured_response is not None,
                    "parsed_response": result["parsed_response"],
                    "files_data": result["files_data"],
                    "conversation_id": result["effective_conv_id"],
                },
            )

        except (
            psycopg.errors.AdminShutdown,
            psycopg.errors.ConnectionFailure,
            psycopg.OperationalError,
        ) as exc:
            # Stale pool connection terminated by PostgreSQL (e.g. server
            # restart or pg_terminate_backend). The pool discards the bad
            # connection automatically; a single retry will receive a fresh one.
            logger.warning(
                "Checkpointer connection lost (%s), retrying once: %s",
                type(exc).__name__,
                str(exc),
            )
            metrics_status, metrics_error_code = "ERROR", type(exc).__name__
            metrics_error_message = "Connection error, please retry."
            terminal_event_yielded = True
            yield AgentStreamEvent(
                "error",
                {"message": "Connection error, please retry."},
                extra={"error_code": metrics_error_code, "error_kind": "connection"},
            )
        except (asyncio.CancelledError, GeneratorExit):
            # Client went away mid-stream -- UNLESS `terminal_event_yielded`
            # is already True, in which case this is `aclosing`/the
            # consumer's own `aclose()` tearing down an already-finished
            # generator right after its terminal event, not a real
            # cancellation; the outcome recorded above (SUCCESS or a specific
            # ERROR) must stand.
            if not terminal_event_yielded:
                metrics_status, metrics_error_code, metrics_error_message = "ERROR", "Cancelled", "Stream cancelled"
            raise
        except PIIDetectionError as exc:
            # PIIMiddleware(strategy="block"): expected outcome, not a server error.
            metrics_status, metrics_error_code, metrics_error_message = "ERROR", "PIIDetectionError", str(exc)
            terminal_event_yielded = True
            yield AgentStreamEvent(
                "error",
                {"message": pii_blocked_message(exc)},
                extra={"error_code": metrics_error_code, "error_kind": "pii_blocked"},
            )
        except ServiceRetiredError as exc:
            # Expected outcome: the message is built by our own helper (service name, date,
            # admin notice), so it is safe to show. Already logged once by the guard.
            metrics_status, metrics_error_code, metrics_error_message = "ERROR", "SERVICE_RETIRED", exc.message
            terminal_event_yielded = True
            yield AgentStreamEvent(
                "error",
                {"message": exc.message, "code": "service_retired"},
                extra={"error_code": "SERVICE_RETIRED", "error_kind": "service_retired", "detail": exc.message},
            )
        except _AgentStreamSerializationError as exc:
            if turn_config is not None:
                # The text can embed the offending payload (reply content).
                log_turn_failure(
                    logger, "Non-serializable event payload in streaming agent chat", exc, chat_turn=True,
                    agent_id=agent_id, conversation_id=ctx.effective_conv_id if ctx is not None else conversation_id,
                )
            else:
                logger.exception(
                    "Non-serializable event payload in streaming agent chat: %s",
                    str(exc),
                )
            metrics_status, metrics_error_code = "ERROR", "SerializationError"
            metrics_error_message = chat_failure_summary(exc) if turn_config is not None else str(exc)[:2000]
            terminal_event_yielded = True
            yield AgentStreamEvent(
                "error",
                {"message": _AGENT_EXECUTION_FAILED},
                extra={"error_code": metrics_error_code, "error_kind": "serialization"},
            )
        except HTTPException as exc:
            logger.warning(
                "HTTPException during streaming agent chat: status=%s detail=%s",
                exc.status_code,
                exc.detail if exc.status_code < 500 else "<redacted>",
            )
            if not resume_settled and effective_db is not None:
                # Permanent (agent deleted / not runnable): finish instead of releasing to PENDING.
                resume_settled = finish_if_agent_unavailable(effective_db, resume.approval.id, exc)
            metrics_status, metrics_error_code = "ERROR", "HTTPException"
            metrics_error_message = (
                str(exc.detail)[:2000] if exc.status_code < 500 else "Internal error"
            )
            terminal_event_yielded = True
            yield AgentStreamEvent(
                "error",
                {"message": _AGENT_EXECUTION_FAILED},
                extra={
                    "error_code": "HTTPException",
                    "error_kind": "http",
                    "status_code": exc.status_code,
                    "detail": exc.detail if exc.status_code < 500 else None,
                },
            )
        except ChatConversationBusyError as exc:
            # The busy marker was lost while the turn was preparing: another turn may own the conversation.
            logger.warning("Chat turn aborted: the busy marker was lost (%s)", type(exc).__name__)
            metrics_status, metrics_error_code = "ERROR", "CONVERSATION_BUSY"
            metrics_error_message = BUSY_MESSAGE
            terminal_event_yielded = True
            yield AgentStreamEvent(
                "error",
                {"message": BUSY_MESSAGE, "code": "conversation_busy"},
                extra={"error_code": "CONVERSATION_BUSY", "error_kind": "conversation_busy", "detail": BUSY_MESSAGE},
            )
        except GraphRecursionError as exc:
            if turn_config is None or ctx is None:
                # Not a Chat turn: unchanged generic failure.
                log_turn_failure(
                    logger, "Error in streaming agent chat", exc, chat_turn=False,
                    agent_id=agent_id, conversation_id=conversation_id,
                )
                metrics_status, metrics_error_code = "ERROR", type(exc).__name__
                metrics_error_message = str(exc)[:2000]
                terminal_event_yielded = True
                yield AgentStreamEvent(
                    "error",
                    {"message": _AGENT_EXECUTION_FAILED},
                    extra={"error_code": metrics_error_code, "error_kind": "agent_failure"},
                )
            else:
                # Chat: out of graph steps. The conversation, its checkpoint and its sandbox are kept (the router
                # does not discard it), what the sandbox already produced is saved, and the client gets a stable,
                # translatable error (no raw text).
                await self.execution_service.handle_chat_step_limit(ctx, exc)
                metrics_status, metrics_error_code = "ERROR", STEP_LIMIT_ERROR_CODE
                metrics_error_message = STEP_LIMIT_MESSAGE
                terminal_event_yielded = True
                yield AgentStreamEvent(
                    "error",
                    {"message": STEP_LIMIT_MESSAGE, "code": "step_limit_reached"},
                    extra={"error_code": STEP_LIMIT_ERROR_CODE, "error_kind": "step_limit", "detail": STEP_LIMIT_MESSAGE},
                )
        except Exception as exc:
            log_turn_failure(
                logger, "Error in streaming agent chat", exc, chat_turn=turn_config is not None,
                agent_id=agent_id, conversation_id=ctx.effective_conv_id if ctx is not None else conversation_id,
            )
            metrics_status, metrics_error_code = "ERROR", type(exc).__name__
            metrics_error_message = chat_failure_summary(exc) if turn_config is not None else str(exc)[:2000]
            terminal_event_yielded = True
            yield AgentStreamEvent(
                "error",
                {"message": _AGENT_EXECUTION_FAILED},
                extra={"error_code": metrics_error_code, "error_kind": "agent_failure"},
            )

        finally:
            if not resume_settled and effective_db is not None:
                # The run failed or was cancelled after the approval was claimed. If it never
                # consumed the pause the approval is answerable again; otherwise the next
                # attempt finds it stale.
                approvals.release(effective_db, resume.approval.id, metrics_error_message or "Run did not finish")
            if ctx is not None:
                if sandbox_turn_active:
                    self.execution_service._end_sandbox_turn(ctx, db=effective_db)
                self.execution_service._release_turn_lease(ctx)
            if mcp_client:
                logger.info("MCP client will be cleaned up automatically")
            if ctx is not None:
                finished_at = datetime.utcnow()
                record_agent_execution(
                    event_id=event_id,
                    fresh_agent=ctx.fresh_agent,
                    user_context=ctx.user_context,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=int((finished_at - started_at).total_seconds() * 1000),
                    status=metrics_status,
                    error_code=metrics_error_code,
                    error_message=metrics_error_message,
                    result=None,
                    image_files=ctx.image_files or [],
                    message=message,
                    collector=metrics_collector,
                    time_to_first_token_ms=(
                        int((first_token_at - started_at).total_seconds() * 1000)
                        if first_token_at is not None else None
                    ),
                    ai_service_override=turn_config.metrics_service() if turn_config is not None else None,
                )

    async def stream_agent_chat(
        self,
        agent_id: int,
        message: str,
        file_references: list | None = None,
        search_params: dict | None = None,
        user_context: dict | None = None,
        conversation_id: int | None = None,
        db: Session | None = None,
        channel: ApprovalChannel = ApprovalChannel.PLAYGROUND,
        resume: "approvals.ResumeRequest | None" = None,
        turn_config: "ResolvedChatConfig | None" = None,
        on_turn_completed: "TurnCompletedHook | None" = None,
    ) -> AsyncGenerator[str, None]:
        """Stream an agent chat turn as SSE events.

        This is a thin presentation-layer bridge: it is a byte-for-byte SSE
        rendering of :meth:`stream_agent_events`, the canonical streaming
        seam. Every event it yields is one
        ``format_sse_event(ev.type, ev.data)`` string per
        :class:`~tools.streaming_utils.AgentStreamEvent` produced by that
        generator — SSE is a presentation of the typed event stream, not the
        source of truth. See :meth:`stream_agent_events` for the full event
        sequence and semantics.

        Args:
            agent_id: Primary key of the agent to execute.
            message: The user's text message.
            file_references: Pre-resolved file-reference objects as returned by
                ``FileManagementService``.  Each object must expose
                ``filename``, ``content``, ``file_type``, ``file_id``, and
                ``file_path``.
            search_params: Optional silo search parameters forwarded to
                ``create_agent``.
            user_context: Caller context dict (``user_id``, ``app_id``,
                ``email``, …).
            conversation_id: ID of an existing conversation to continue.  When
                ``None`` and the agent has memory enabled a new conversation is
                created automatically.
            db: SQLAlchemy session.  If omitted the instance-level ``self.db``
                is used.
            channel: Where the turn comes from (see :meth:`stream_agent_events`).
            resume: Claimed approval to answer instead of sending ``message``.
            turn_config / on_turn_completed: Flexible-chat override and hook (see
                :meth:`stream_agent_events`).

        Yields:
            SSE-formatted strings (``"data: {...}\\n\\n"``).
        """
        async with contextlib.aclosing(
            self.stream_agent_events(
                agent_id,
                message,
                file_references=file_references,
                search_params=search_params,
                user_context=user_context,
                conversation_id=conversation_id,
                db=db,
                channel=channel,
                resume=resume,
                turn_config=turn_config,
                on_turn_completed=on_turn_completed,
            )
        ) as events:
            async for ev in events:
                yield format_sse_event(ev.type, ev.data)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _finalize(self, ctx, raw_response, db, chat_turn: bool, finalize_kwargs: dict) -> dict:
        """Run ``_finalize_turn``; for a chat turn, to completion even if the consumer goes away.

        A disconnected client would otherwise leave the answer in the checkpoint with no turn
        bookkeeping. Starlette's ``StreamingResponse`` runs inside an anyio task group and, on
        disconnect, cancels it by re-delivering the cancellation on every event-loop turn, so an
        ``asyncio.shield`` + wait cannot survive it (the router would close the DB session under
        the still-running work). Instead the work runs inside a *shielded anyio cancel scope*
        with a deadline (``FINALIZE_GRACE_S``): outer cancellation is held back until it finishes
        (the request session is closed by the router only afterwards) and is delivered at the
        next checkpoint. If the deadline is hit, the work is cancelled, an ERROR is logged and
        the turn is reported as failed (not finalized). Standard turns await directly (as before).
        """
        if not chat_turn:
            return await self.execution_service._finalize_turn(ctx, raw_response, db, **finalize_kwargs)
        # The sandbox output pull has its own (shielded) time budget and never raises: a slow or failing pull
        # must not eat the finalize grace window nor turn a completed answer into a failed turn.
        with anyio.CancelScope(shield=True):
            await self.execution_service._pull_outputs(ctx)
        with anyio.CancelScope(shield=True) as scope:
            scope.deadline = anyio.current_time() + FINALIZE_GRACE_S
            result = await self.execution_service._finalize_turn(ctx, raw_response, db, **finalize_kwargs)
        if scope.cancelled_caught:
            logger.error(
                "Chat turn finalization exceeded %ss for conversation %s; turn not finalized",
                FINALIZE_GRACE_S, getattr(ctx, "effective_conv_id", None),
            )
            raise TimeoutError("Chat turn finalization timed out")
        # Surface a pending outer cancellation (client gone) now that the bookkeeping is done.
        await anyio.lowlevel.checkpoint()
        return result
