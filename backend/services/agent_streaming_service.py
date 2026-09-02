"""
Streaming agent execution service.

A thin SSE adapter over AgentExecutionService.  The setup and post-processing
phases are fully delegated to AgentExecutionService._prepare_turn() and
_finalize_turn(); this service only owns the astream loop that yields tokens
and tool events to the client.
"""

from typing import AsyncGenerator, Dict, List, Any

import psycopg.errors
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
from services.agent_cache_service import (
    CheckpointerCacheService,
    is_missing_tool_output_error,
)
from utils.logger import get_logger

logger = get_logger(__name__)


async def _has_pending_interrupt(agent_chain, config) -> bool:
    """True when the graph is parked on a HITL interrupt awaiting a decision."""
    try:
        state = await agent_chain.aget_state(config)
        return any(getattr(task, "interrupts", None) for task in getattr(state, "tasks", []))
    except Exception as exc:
        # ponytail: unreadable state falls back to "no interrupt" so the caller's
        # existing recovery path stays reachable.
        logger.warning("Could not read graph state for pending interrupts: %s", exc)
        return False


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
    ) -> AsyncGenerator[str, None]:
        """Stream an agent chat turn as SSE events.

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

            # ----------------------------------------------------------------
            # 2. Emit early metadata event so the client has conversation_id
            # ----------------------------------------------------------------
            yield format_sse_event(
                "metadata",
                {
                    "conversation_id": ctx.effective_conv_id,
                    "agent_id": agent_id,
                    "agent_name": ctx.agent.name,
                    "has_memory": ctx.agent.has_memory,
                },
            )

            accumulated_content = ""
            structured_response = None

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
                    async for mode, chunk in agent_chain.astream(
                        {"messages": [message_payload]},
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
                                    accumulated_content += event["data"].get("content", "")
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
                        and not await _has_pending_interrupt(agent_chain, config)
                    ):
                        logger.warning(
                            "Detected incomplete tool-call checkpoint for agent %s "
                            "session %s; deleting checkpoint and retrying turn once",
                            ctx.fresh_agent.agent_id,
                            ctx.session_id_for_cache,
                        )
                        await CheckpointerCacheService.invalidate_checkpointer_async(
                            ctx.fresh_agent.agent_id,
                            ctx.session_id_for_cache,
                        )
                        continue
                    raise

            raw_response = (
                structured_response
                if structured_response is not None
                else accumulated_content
            )
            logger.info("Stream completed — accumulated_content length=%d", len(accumulated_content))

            # Check for pending interrupts after stream completes
            has_pending_interrupt = False
            try:
                graph_state = await agent_chain.aget_state(config)
                if hasattr(graph_state, 'tasks'):
                    for task in graph_state.tasks:
                        if hasattr(task, 'interrupts') and task.interrupts:
                            has_pending_interrupt = True
                            logger.info("PENDING INTERRUPT found in graph state: %s", task.interrupts)
                            for intr in task.interrupts:
                                payload = intr.value if hasattr(intr, 'value') else intr
                                action_requests = []
                                review_configs = []
                                if isinstance(payload, dict):
                                    action_requests = payload.get("action_requests", [])
                                    review_configs = payload.get("review_configs", [])
                                yield format_sse_event(
                                    "hitl_interrupt",
                                    {
                                        "action_requests": action_requests,
                                        "review_configs": review_configs,
                                    },
                                )
            except Exception as state_err:
                logger.warning("Could not check graph state for interrupts: %s", state_err)

            # If HITL interrupted, emit done with interrupt message and skip normal finalization
            if has_pending_interrupt:
                yield format_sse_event(
                    "done",
                    {
                        "response": "⏸️ Execution paused — awaiting human approval.",
                        "conversation_id": ctx.effective_conv_id,
                        "files": [],
                        "hitl_paused": True,
                    },
                )
            else:
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
            yield format_sse_event("error", {"message": "Connection error, please retry."})
        except Exception as exc:
            # Check if this is a GraphInterrupt from HumanInTheLoop middleware
            from langgraph.errors import GraphInterrupt
            if isinstance(exc, GraphInterrupt):
                interrupts = getattr(exc, "interrupts", [])
                logger.info(
                    "GraphInterrupt caught — HITL middleware paused execution. "
                    "Interrupts: %s", interrupts
                )
                # Emit HITL interrupt event to the frontend
                for intr in interrupts:
                    payload = intr.value if hasattr(intr, "value") else intr
                    action_requests = []
                    review_configs = []
                    if isinstance(payload, dict):
                        action_requests = payload.get("action_requests", [])
                        review_configs = payload.get("review_configs", [])
                    yield format_sse_event(
                        "hitl_interrupt",
                        {
                            "action_requests": action_requests,
                            "review_configs": review_configs,
                        },
                    )
                # Emit done with a placeholder so the UI shows the interrupt message
                yield format_sse_event(
                    "done",
                    {
                        "response": "⏸️ Execution paused — awaiting human approval.",
                        "conversation_id": ctx.effective_conv_id if ctx else None,
                        "files": [],
                        "hitl_paused": True,
                    },
                )
            else:
                logger.error("Error in streaming agent chat: %s", str(exc), exc_info=True)
                yield format_sse_event("error", {"message": str(exc)})

        finally:
            if ctx is not None and sandbox_turn_active:
                self.execution_service._end_sandbox_turn(ctx, db=effective_db)
            if mcp_client:
                logger.info("MCP client will be cleaned up automatically")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def stream_resume_agent_chat(
        self,
        agent_id: int,
        decisions: list[dict],
        user_context: dict | None = None,
        conversation_id: int | None = None,
        db: Session | None = None,
    ) -> AsyncGenerator[str, None]:
        """Resume a HITL-interrupted agent turn by sending decisions back.

        After a ``hitl_interrupt`` event paused the graph, the client calls
        this method with the user's decisions (approve / edit / reject) to
        resume execution from the saved checkpoint.

        Yields:
            SSE-formatted strings identical to ``stream_agent_chat``.
        """
        from langgraph.types import Command

        effective_db = db or self.db
        mcp_client = None
        ctx = None

        try:
            # 1. Prepare turn (reuses same session / conversation)
            ctx = await self.execution_service._prepare_turn(
                agent_id=agent_id,
                message="",  # No new user message for resume
                user_context=user_context,
                conversation_id=conversation_id,
                db=effective_db,
            )

            yield format_sse_event(
                "metadata",
                {
                    "conversation_id": ctx.effective_conv_id,
                    "session_id": ctx.conversation.session_id if ctx.conversation else None,
                    "agent_id": agent_id,
                    "agent_name": ctx.agent.name,
                    "has_memory": ctx.agent.has_memory,
                },
            )

            # 2. Rebuild agent chain (same tools, same checkpointer)
            agent_chain, mcp_client = await create_agent(
                ctx.fresh_agent,
                ctx.search_params,
                ctx.session_id_for_cache,
                ctx.user_context,
                ctx.working_dir,
            )

            config = prepare_agent_config(ctx.fresh_agent)
            config["configurable"]["thread_id"] = compute_thread_id(ctx.fresh_agent, ctx.session_id_for_cache)

            # 3. Build the Command to resume with decisions
            resume_value = {"decisions": decisions}
            resume_input = Command(resume=resume_value)

            logger.info(
                "Resuming HITL for agent %s with %d decision(s): %s",
                agent_id, len(decisions),
                [d.get("type") for d in decisions],
            )

            # 4. Stream resumed execution
            accumulated_content = ""

            async for mode, chunk in agent_chain.astream(
                resume_input,
                config=config,
                stream_mode=["messages", "updates", "custom"],
            ):
                events = map_stream_event(mode, chunk)
                if events:
                    for event in events:
                        if event["type"] == SSE_TOKEN:
                            accumulated_content += event["data"].get("content", "")
                        yield format_sse_event(event["type"], event["data"])

            # 5. Check for further interrupts (chained HITL)
            has_pending_interrupt = False
            try:
                graph_state = await agent_chain.aget_state(config)
                for task in getattr(graph_state, 'tasks', []):
                    if hasattr(task, 'interrupts') and task.interrupts:
                        has_pending_interrupt = True
                        for intr in task.interrupts:
                            payload = intr.value if hasattr(intr, 'value') else intr
                            if isinstance(payload, dict):
                                action_requests = payload.get("action_requests", [])
                                review_configs = payload.get("review_configs", [])
                            else:
                                action_requests = []
                                review_configs = []
                            yield format_sse_event(
                                "hitl_interrupt",
                                {
                                    "action_requests": action_requests,
                                    "review_configs": review_configs,
                                },
                            )
            except Exception as state_err:
                logger.warning("Could not check graph state after resume: %s", state_err)

            if has_pending_interrupt:
                yield format_sse_event(
                    "done",
                    {
                        "response": "⏸️ Execution paused — awaiting human approval.",
                        "conversation_id": ctx.effective_conv_id,
                        "files": [],
                        "hitl_paused": True,
                    },
                )
            else:
                # 6. Normal finalization
                result = await self.execution_service._finalize_turn(
                    ctx, accumulated_content, effective_db
                )
                yield format_sse_event(
                    "done",
                    {
                        "response": result["parsed_response"],
                        "conversation_id": result["effective_conv_id"],
                        "files": result["files_data"],
                    },
                )

        except Exception as exc:
            logger.error("Error resuming HITL agent chat: %s", str(exc), exc_info=True)
            yield format_sse_event("error", {"message": str(exc)})

        finally:
            if mcp_client:
                logger.info("MCP client will be cleaned up automatically")
