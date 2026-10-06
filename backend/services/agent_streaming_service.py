"""
Streaming agent execution service.

``stream_agent_events`` is the canonical streaming seam (AD-5): it owns the
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
from typing import AsyncGenerator, Dict, List, Any

import psycopg.errors
from fastapi import HTTPException
from sqlalchemy.orm import Session

from tools.agentTools import create_agent, prepare_agent_config, build_human_message
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
)
from services.agent_execution_service import AgentExecutionService
from services.agent_metrics_collector import AgentMetricsCollector
from services.agent_metrics_recorder import record_agent_execution
from services.agent_cache_service import (
    CheckpointerCacheService,
    is_missing_tool_output_error,
)
from utils.logger import get_logger

logger = get_logger(__name__)


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
    ) -> AsyncGenerator[AgentStreamEvent, None]:
        """Run one agent chat turn and yield typed stream events.

        This is the **canonical streaming seam** (AD-5): it runs exactly the
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
           ``"agent_failure"``) a non-SSE consumer can switch on.

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
              per successful or failed turn; on cancellation
              (``CancelledError``/``GeneratorExit``) neither is yielded —
              the generator re-raises instead, after recording the turn as
              ``"Cancelled"``.
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

        Yields:
            :class:`~tools.streaming_utils.AgentStreamEvent` instances.
        """
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
            )
            sandbox_turn_active = self.execution_service._begin_sandbox_turn(
                ctx,
                db=effective_db,
            )
            # Sub-agents built as tools read current_event_id to link their runs to this one.
            ctx.user_context = {**(ctx.user_context or {}), "current_event_id": event_id}

            # ----------------------------------------------------------------
            # 2. Emit early metadata event so the client has conversation_id
            # ----------------------------------------------------------------
            yield AgentStreamEvent(
                "metadata",
                {
                    "conversation_id": ctx.effective_conv_id,
                    "session_id": (
                        getattr(ctx.conversation, "session_id", None)
                        if getattr(ctx, "conversation", None)
                        else None
                    ),
                    "agent_id": agent_id,
                    "agent_name": ctx.agent.name,
                    "has_memory": ctx.agent.has_memory,
                },
            )

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
                )
                agent_chain, mcp_client = create_agent_result[:2]

                config = prepare_agent_config(ctx.fresh_agent)

                if ctx.fresh_agent.has_memory and ctx.session_id_for_cache:
                    config["configurable"]["thread_id"] = (
                        f"thread_{ctx.fresh_agent.agent_id}_{ctx.session_id_for_cache}"
                    )
                    logger.info(
                        "Using session-aware thread_id: %s",
                        config["configurable"]["thread_id"],
                    )
                else:
                    config["configurable"]["thread_id"] = (
                        f"thread_{ctx.fresh_agent.agent_id}"
                    )

                config["configurable"]["question"] = ctx.enhanced_message
                if rollback_checkpoint_id is not None:
                    config["configurable"]["checkpoint_id"] = rollback_checkpoint_id
                config.setdefault("callbacks", []).append(metrics_collector)

                # ------------------------------------------------------------
                # 4. Build the HumanMessage payload (handles multimodal images)
                # ------------------------------------------------------------
                message_payload = build_human_message(
                    ctx.fresh_agent, ctx.enhanced_message, ctx.image_files, ctx.user_context
                )

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
                if effective_db is not None:
                    effective_db.commit()

                accumulated_content = ""
                structured_response = None

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
                            {"messages": [message_payload]},
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

                            events = map_stream_event(mode, chunk)
                            if events:
                                for event in events:
                                    if event["type"] == SSE_TOKEN:
                                        if first_token_at is None:
                                            first_token_at = datetime.utcnow()
                                        accumulated_content += event["data"].get("content", "")
                                    yield AgentStreamEvent(event["type"], event["data"])
                    break
                except Exception as stream_exc:
                    if (
                        attempt == 0
                        and ctx.fresh_agent.has_memory
                        and ctx.session_id_for_cache
                        and is_missing_tool_output_error(stream_exc)
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
                            metrics_error_message = str(stream_exc)[:2000]
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

            # ----------------------------------------------------------------
            # 7. Post-processing phase — delegates to AgentExecutionService
            # ----------------------------------------------------------------

            raw_response = (
                structured_response
                if structured_response is not None
                else accumulated_content
            )

            result = await self.execution_service._finalize_turn(
                ctx, raw_response, effective_db
            )

            # ----------------------------------------------------------------
            # 8. Emit done event
            # ----------------------------------------------------------------
            done_data = {
                "response": result["parsed_response"],
                "conversation_id": result["effective_conv_id"],
                "files": result["files_data"],
            }
            # Validate up front rather than let format_sse_event's json.dumps
            # raise inside the SSE bridge: a failure there would surface
            # through contextlib.aclosing's teardown of this generator and
            # get misreported as a cancellation instead of a real error, and
            # no SSE error event would ever reach the client.
            _assert_json_serializable(done_data, event_type="done")
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
            yield AgentStreamEvent(
                "error",
                {"message": "Connection error, please retry."},
                extra={"error_code": metrics_error_code, "error_kind": "connection"},
            )
        except (asyncio.CancelledError, GeneratorExit):
            # Client went away mid-stream.
            metrics_status, metrics_error_code, metrics_error_message = "ERROR", "Cancelled", "Stream cancelled"
            raise
        except _AgentStreamSerializationError as exc:
            logger.error(
                "Non-serializable event payload in streaming agent chat: %s",
                str(exc),
                exc_info=True,
            )
            metrics_status, metrics_error_code = "ERROR", "SerializationError"
            metrics_error_message = str(exc)[:2000]
            yield AgentStreamEvent(
                "error",
                {"message": "Agent execution failed"},
                extra={"error_code": metrics_error_code, "error_kind": "serialization"},
            )
        except HTTPException as exc:
            logger.warning(
                "HTTPException during streaming agent chat: status=%s detail=%s",
                exc.status_code,
                exc.detail if exc.status_code < 500 else "<redacted>",
            )
            metrics_status, metrics_error_code = "ERROR", "HTTPException"
            metrics_error_message = (
                str(exc.detail)[:2000] if exc.status_code < 500 else "Internal error"
            )
            yield AgentStreamEvent(
                "error",
                {"message": "Agent execution failed"},
                extra={
                    "error_code": "HTTPException",
                    "error_kind": "http",
                    "status_code": exc.status_code,
                    "detail": exc.detail if exc.status_code < 500 else None,
                },
            )
        except Exception as exc:
            logger.error("Error in streaming agent chat: %s", str(exc), exc_info=True)
            metrics_status, metrics_error_code = "ERROR", type(exc).__name__
            metrics_error_message = str(exc)[:2000]
            yield AgentStreamEvent(
                "error",
                {"message": "Agent execution failed"},
                extra={"error_code": metrics_error_code, "error_kind": "agent_failure"},
            )

        finally:
            if ctx is not None and sandbox_turn_active:
                self.execution_service._end_sandbox_turn(ctx, db=effective_db)
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
    ) -> AsyncGenerator[str, None]:
        """Stream an agent chat turn as SSE events.

        This is a thin presentation-layer bridge: it is a byte-for-byte SSE
        rendering of :meth:`stream_agent_events`, the canonical streaming
        seam (AD-5). Every event it yields is one
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
            )
        ) as events:
            async for ev in events:
                yield format_sse_event(ev.type, ev.data)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
