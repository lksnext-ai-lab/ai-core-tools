"""
Streaming agent execution service.

A thin SSE adapter over AgentExecutionService.  The setup and post-processing
phases are fully delegated to AgentExecutionService._prepare_turn() and
_finalize_turn(); this service only owns the astream loop that yields tokens
and tool events to the client.
"""

import asyncio
import uuid
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Any

import psycopg.errors
from langchain_core.messages import AIMessage
from langgraph.types import Command
from sqlalchemy.orm import Session

from tools.agentTools import create_agent, prepare_agent_config, build_human_message, compute_thread_id
from tools.langsmith_config import (
    apply_tracing_to_config,
    build_tracing_config,
    resolve_langsmith_settings,
)
from tools.streaming_utils import (
    format_sse_event,
    map_stream_event,
    SSE_TOKEN,
    SSE_HITL_INTERRUPT,
)
from services.agent_execution_service import AgentExecutionService
from services.hitl_service import HITLDecisionError, pending_approval_from_state, validate_decisions
from tools.middleware.factory import human_in_the_loop_config, redacts_output
from services.agent_metrics_collector import AgentMetricsCollector
from services.agent_metrics_recorder import record_agent_execution
from services.agent_cache_service import (
    CheckpointerCacheService,
    is_missing_tool_output_error,
)
from utils.logger import get_logger

logger = get_logger(__name__)


async def _pending_approval(agent_chain, config) -> dict | None:
    """The HITL request the graph is paused on, or None."""
    try:
        return pending_approval_from_state(await agent_chain.aget_state(config))
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


class AgentStreamingService:
    """Service for streaming agent responses via Server-Sent Events."""

    def __init__(self, db: Session = None) -> None:
        self.execution_service = AgentExecutionService()
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def stream_agent_chat(
        self,
        agent_id: int,
        message: str,
        file_references: list | None = None,
        search_params: dict | None = None,
        user_context: dict | None = None,
        conversation_id: int | None = None,
        db: Session | None = None,
        resume_decisions: list[dict] | None = None,
        approval_ui: bool = True,
    ) -> AsyncGenerator[str, None]:
        """Stream an agent chat turn as SSE events.

        With ``resume_decisions`` the turn resumes a human-in-the-loop pause instead of
        sending a new message: the decisions are validated against the pending approval
        and passed to the graph as ``Command(resume={"decisions": ...})``.
        Callers whose UI cannot collect a decision pass ``approval_ui=False`` and get an
        ``error`` event instead of a pause they could never resume.

        Yields ``format_sse_event`` strings for each event in the following
        sequence:

        1. ``metadata`` — emitted immediately after setup with conversation/agent
           metadata so the client can bind the conversation ID before tokens
           arrive.
        2. ``thinking`` / ``tool_start`` / ``tool_end`` — emitted while the agent
           reasons and calls tools.
        3. ``token`` — one per partial LLM text chunk.
        4. ``done`` — emitted once after the stream finishes, carrying the full
           parsed response, conversation ID, and any generated files.
        5. ``error`` — emitted instead of ``done`` if an unhandled exception
           occurs.

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
            yield format_sse_event(
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
                config["configurable"]["thread_id"] = compute_thread_id(
                    ctx.fresh_agent, ctx.session_id_for_cache
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
                if resume_decisions is None:
                    stream_input = {"messages": [build_human_message(
                        ctx.fresh_agent, ctx.enhanced_message, ctx.image_files, ctx.user_context
                    )]}
                else:
                    try:
                        validate_decisions(await _pending_approval(agent_chain, config), resume_decisions)
                    except HITLDecisionError as exc:
                        metrics_status, metrics_error_code, metrics_error_message = "ERROR", "HITLDecisionError", str(exc)
                        yield format_sse_event("error", {"message": str(exc)})
                        return
                    stream_input = Command(resume={"decisions": resume_decisions})

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
                # PIIMiddleware(apply_to_output) redacts the AI message in after_model, i.e.
                # after its tokens were streamed; hold tokens back so PII never reaches the UI.
                buffer_output = redacts_output(ctx.fresh_agent)
                hitl_enabled = human_in_the_loop_config(ctx.fresh_agent) is not None

                try:
                    async for mode, chunk in agent_chain.astream(
                        stream_input,
                        config=config,
                        stream_mode=["messages", "updates", "custom"],
                    ):

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
                                    if buffer_output:
                                        # Raw tokens are not PII-redacted yet; send the
                                        # redacted final message instead (see below).
                                        continue
                                yield format_sse_event(event["type"], event["data"])
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
                        and not (hitl_enabled and await _pending_approval(agent_chain, config))
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
                            yield format_sse_event(
                                "error",
                                {"message": "Your last message could not be completed. Please resend it."},
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
            pending = await _pending_approval(agent_chain, config) if hitl_enabled else None
            if pending and not approval_ui:
                tools = ", ".join(a["name"] for a in pending["action_requests"])
                metrics_status, metrics_error_code = "ERROR", "HumanApprovalRequired"
                metrics_error_message = f"Approval required for {tools}"
                yield format_sse_event("error", {
                    "message": f"This agent needs human approval before running {tools}, "
                               "which is not available in this chat.",
                })
                return
            if pending:
                # Paused by HumanInTheLoopMiddleware: nothing to finalize until the
                # reviewer answers through the resume endpoint.
                yield format_sse_event(SSE_HITL_INTERRUPT, pending)
                yield format_sse_event(
                    "done",
                    {"response": "", "conversation_id": ctx.effective_conv_id, "files": [], "hitl_paused": True},
                )
                return

            if buffer_output and structured_response is None:
                raw_response = await _final_answer_text(agent_chain, config)

            # ----------------------------------------------------------------
            # 7. Post-processing phase — delegates to AgentExecutionService
            # ----------------------------------------------------------------
            result = await self.execution_service._finalize_turn(
                ctx, raw_response, effective_db
            )

            # ----------------------------------------------------------------
            # 8. Emit done event
            # ----------------------------------------------------------------
            yield format_sse_event(
                "done",
                {
                    "response": result["parsed_response"],
                    "conversation_id": result["effective_conv_id"],
                    "files": result["files_data"],
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
            yield format_sse_event("error", {"message": "Connection error, please retry."})
        except (asyncio.CancelledError, GeneratorExit):
            # Client went away mid-stream.
            metrics_status, metrics_error_code, metrics_error_message = "ERROR", "Cancelled", "Stream cancelled"
            raise
        except Exception as exc:
            logger.error("Error in streaming agent chat: %s", str(exc), exc_info=True)
            metrics_status, metrics_error_code = "ERROR", type(exc).__name__
            metrics_error_message = str(exc)[:2000]
            yield format_sse_event("error", {"message": "Agent execution failed"})

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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
