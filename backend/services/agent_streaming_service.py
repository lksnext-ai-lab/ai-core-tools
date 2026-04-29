"""
Streaming agent execution service.

A thin SSE adapter over AgentExecutionService.  The setup and post-processing
phases are fully delegated to AgentExecutionService._prepare_turn() and
_finalize_turn(); this service only owns the astream loop that yields tokens
and tool events to the client.
"""

from typing import AsyncGenerator, Dict, List, Any

import langsmith as ls
from sqlalchemy.orm import Session

from tools.agentTools import create_agent, prepare_agent_config, build_human_message
from tools.streaming_utils import (
    format_sse_event,
    map_stream_event,
    SSE_TOKEN,
)
from services.a2a_executor_service import A2AExecutionResult, A2AExecutorService
from services.a2a_service import A2AService
from services.agent_execution_service import AgentExecutionService
from utils.logger import get_logger

logger = get_logger(__name__)


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

            if A2AService.is_a2a_agent(ctx.fresh_agent):
                logger.info(
                    "Routing streaming execution to A2A executor for agent_id=%s conversation_id=%s",
                    ctx.fresh_agent.agent_id,
                    ctx.effective_conv_id,
                )
                accumulated_content = ""
                remote_result = None
                executor = A2AExecutorService()

                async for event in executor.stream(
                    ctx.fresh_agent,
                    ctx.enhanced_message,
                    user_context=ctx.user_context,
                    attachment_files=ctx.processed_files,
                    memory_context=ctx.a2a_memory_context,
                ):
                    if event["type"] == SSE_TOKEN:
                        accumulated_content += event["data"].get("content", "")
                    elif event["type"] == "final":
                        remote_result = A2AExecutionResult(
                            text=event["data"].get("content", ""),
                            remote_task_id=event["data"].get("remote_task_id"),
                            remote_context_id=event["data"].get("remote_context_id"),
                            remote_task_state=event["data"].get("remote_task_state"),
                        )
                    yield format_sse_event(event["type"], event["data"])

                if remote_result is not None:
                    self.execution_service._apply_a2a_remote_state(
                        ctx,
                        remote_result,
                        effective_db,
                    )

                final_response_text = accumulated_content or (
                    remote_result.text if remote_result else ""
                )
                await self.execution_service._persist_a2a_history(
                    ctx,
                    final_response_text,
                )

                if effective_db:
                    A2AService.update_health(
                        effective_db,
                        ctx.fresh_agent.a2a_config,
                        healthy=True,
                    )

                result = await self.execution_service._finalize_turn(
                    ctx,
                    final_response_text,
                    effective_db,
                )

                yield format_sse_event(
                    "done",
                    {
                        "response": result["parsed_response"],
                        "conversation_id": result["effective_conv_id"],
                        "files": result["files_data"],
                    },
                )
                return

            # ----------------------------------------------------------------
            # 3. Build agent chain
            # ----------------------------------------------------------------
            agent_chain, langsmith_config, mcp_client = await create_agent(
                ctx.fresh_agent,
                ctx.search_params,
                ctx.session_id_for_cache,
                ctx.user_context,
                ctx.working_dir,
            )

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

            # ----------------------------------------------------------------
            # 4. Build the HumanMessage payload (handles multimodal images)
            # ----------------------------------------------------------------
            message_payload = build_human_message(
                ctx.fresh_agent, ctx.enhanced_message, ctx.image_files, ctx.user_context
            )

            # ----------------------------------------------------------------
            # 5. Attach LangSmith tracer when configured
            # ----------------------------------------------------------------
            if langsmith_config:
                from langchain_core.tracers.langchain import LangChainTracer

                logger.info(
                    "LangSmith tracing ENABLED for app '%s'",
                    langsmith_config["project_name"],
                )
                per_app_tracer = LangChainTracer(
                    client=langsmith_config["client"],
                    project_name=langsmith_config["project_name"],
                )
                config.setdefault("callbacks", []).append(per_app_tracer)

            # ----------------------------------------------------------------
            # 6. Streaming loop — the only part that stays in this service
            # ----------------------------------------------------------------
            accumulated_content = ""

            if langsmith_config:
                stream_ctx = ls.tracing_context(
                    client=langsmith_config["client"],
                    project_name=langsmith_config["project_name"],
                    enabled=True,
                )
            else:
                from contextlib import nullcontext

                stream_ctx = nullcontext()

            with stream_ctx:
                async for mode, chunk in agent_chain.astream(
                    {"messages": [message_payload]},
                    config=config,
                    stream_mode=["messages", "updates"],
                ):
                    events = map_stream_event(mode, chunk)
                    if events:
                        for event in events:
                            if event["type"] == SSE_TOKEN:
                                accumulated_content += event["data"].get("content", "")
                            yield format_sse_event(event["type"], event["data"])

            # ----------------------------------------------------------------
            # 7. Post-processing phase — delegates to AgentExecutionService
            # ----------------------------------------------------------------
            result = await self.execution_service._finalize_turn(
                ctx, accumulated_content, effective_db
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

        except Exception as exc:
            if effective_db and 'ctx' in locals() and ctx and A2AService.is_a2a_agent(ctx.fresh_agent):
                A2AService.update_health(
                    effective_db,
                    ctx.fresh_agent.a2a_config,
                    healthy=False,
                    error_summary=str(exc),
                )
            logger.error("Error in streaming agent chat: %s", str(exc), exc_info=True)
            yield format_sse_event("error", {"message": str(exc)})

        finally:
            if mcp_client:
                logger.info("MCP client will be cleaned up automatically")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
