"""
Streaming agent execution service.

Mirrors AgentExecutionService.execute_agent_chat_with_file_refs() but yields
SSE-formatted events instead of returning a complete response.  The setup phase
(agent lookup, conversation management, working-dir resolution) is identical to
the non-streaming path.  The difference is that _execute_agent_async()'s
ainvoke() call is replaced by astream() with stream_mode=["messages", "updates"].
"""

import os
import re
import base64
import mimetypes
from typing import AsyncGenerator, Dict, List, Optional, Any

import langsmith as ls
from langchain.messages import HumanMessage
from sqlalchemy.orm import Session
from fastapi import HTTPException

from models.agent import Agent
from tools.agentTools import create_agent, prepare_agent_config, parse_agent_response
from tools.streaming_utils import (
    format_sse_event,
    map_stream_event,
    SSE_TOKEN,
)
from services.agent_service import AgentService
from services.session_management_service import SessionManagementService
from services.file_management_service import FileManagementService
from services.agent_execution_service import AgentExecutionService, _inject_file_markers
from repositories.agent_execution_repository import AgentExecutionRepository
from utils.logger import get_logger
from utils.config import get_app_config

logger = get_logger(__name__)


class AgentStreamingService:
    """Service for streaming agent responses via Server-Sent Events."""

    def __init__(self, db: Session = None) -> None:
        self.agent_service = AgentService()
        self.session_service = SessionManagementService()
        self.agent_execution_repo = AgentExecutionRepository()
        # Reuse the existing execution service for shared helpers
        self.execution_service = AgentExecutionService(db)
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
            # 1. Resolve agent + validate access
            # ----------------------------------------------------------------
            agent = self.agent_service.get_agent(effective_db, agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")

            await self.execution_service._validate_agent_access(agent, user_context)

            # ----------------------------------------------------------------
            # 2. Process file references
            # ----------------------------------------------------------------
            processed_files: List[Dict[str, Any]] = []
            if file_references:
                for file_ref in file_references:
                    processed_files.append(
                        {
                            "filename": file_ref.filename,
                            "content": file_ref.content,
                            "type": file_ref.file_type,
                            "file_id": file_ref.file_id,
                            "file_path": file_ref.file_path,
                        }
                    )

            # ----------------------------------------------------------------
            # 3. Get / create conversation for memory-enabled agents
            # ----------------------------------------------------------------
            session = None
            conversation = None
            if agent.has_memory:
                from services.conversation_service import ConversationService  # local import to avoid circular

                if conversation_id:
                    conversation = ConversationService.get_conversation(
                        db=effective_db,
                        conversation_id=conversation_id,
                        user_context=user_context,
                        agent_id=agent_id,
                    )
                    if not conversation:
                        raise HTTPException(
                            status_code=404,
                            detail="Conversation not found or access denied",
                        )
                    session_suffix = conversation.session_id.replace(
                        f"conv_{agent_id}_", ""
                    )
                    session = await self.session_service.get_user_session(
                        agent_id=agent_id,
                        user_context=user_context,
                        conversation_id=session_suffix,
                    )
                else:
                    conversation = ConversationService.create_conversation(
                        db=effective_db,
                        agent_id=agent_id,
                        user_context=user_context,
                        title=None,
                    )
                    logger.info(
                        "Auto-created conversation %s for agent %s",
                        conversation.conversation_id,
                        agent_id,
                    )
                    session_suffix = conversation.session_id.replace(
                        f"conv_{agent_id}_", ""
                    )
                    session = await self.session_service.get_user_session(
                        agent_id=agent_id,
                        user_context=user_context,
                        conversation_id=session_suffix,
                    )

            # ----------------------------------------------------------------
            # 4. Re-query agent with all relationships eagerly loaded
            # ----------------------------------------------------------------
            fresh_agent = self.agent_execution_repo.get_agent_with_relationships(
                effective_db, agent_id
            )
            if not fresh_agent:
                raise HTTPException(
                    status_code=404, detail="Agent not found in database"
                )

            # ----------------------------------------------------------------
            # 5. Prepare message + working directory
            # ----------------------------------------------------------------
            enhanced_message, image_files = (
                self.execution_service._prepare_message_with_files(
                    message, processed_files
                )
            )

            session_id_for_cache = (
                session.id if (fresh_agent.has_memory and session) else None
            )

            effective_conv_id: int | None = conversation_id or (
                conversation.conversation_id if conversation else None
            )

            app_config = get_app_config()
            tmp_base = app_config["TMP_BASE_FOLDER"]
            if effective_conv_id:
                working_dir = os.path.join(
                    tmp_base, "conversations", str(effective_conv_id)
                )
            else:
                user_id = (
                    user_context.get("user_id", "anonymous")
                    if user_context
                    else "anonymous"
                )
                app_id_ctx = (
                    user_context.get("app_id", "default")
                    if user_context
                    else "default"
                )
                session_key = f"agent_{agent_id}_user_{user_id}_app_{app_id_ctx}"
                working_dir = os.path.join(tmp_base, "persistent", session_key)

            # ----------------------------------------------------------------
            # 6. Emit early metadata event so the client has conversation_id
            # ----------------------------------------------------------------
            yield format_sse_event(
                "metadata",
                {
                    "conversation_id": effective_conv_id,
                    "agent_id": agent_id,
                    "agent_name": agent.name,
                    "has_memory": agent.has_memory,
                },
            )

            # ----------------------------------------------------------------
            # 7. Build agent chain
            # ----------------------------------------------------------------
            agent_chain, langsmith_config, mcp_client = await create_agent(
                fresh_agent,
                search_params,
                session_id_for_cache,
                user_context,
                working_dir,
            )

            config = prepare_agent_config(fresh_agent)

            if fresh_agent.has_memory and session_id_for_cache:
                config["configurable"]["thread_id"] = (
                    f"thread_{fresh_agent.agent_id}_{session_id_for_cache}"
                )
                logger.info(
                    "Using session-aware thread_id: %s",
                    config["configurable"]["thread_id"],
                )
            else:
                config["configurable"]["thread_id"] = (
                    f"thread_{fresh_agent.agent_id}"
                )

            config["configurable"]["question"] = enhanced_message

            # ----------------------------------------------------------------
            # 8. Build the HumanMessage payload (handles multimodal images)
            # ----------------------------------------------------------------
            message_payload = self._build_message_payload(
                fresh_agent, enhanced_message, image_files, user_context
            )

            # ----------------------------------------------------------------
            # 9. Attach LangSmith tracer when configured
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
            # 10. Streaming loop
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
                                accumulated_content += event["data"].get(
                                    "content", ""
                                )
                            yield format_sse_event(event["type"], event["data"])

            # ----------------------------------------------------------------
            # 11. Post-processing: sync output files
            # ----------------------------------------------------------------
            response = accumulated_content
            files_data: List[Dict[str, Any]] = []

            if working_dir:
                file_service = FileManagementService()
                new_files = await file_service.sync_output_files(
                    working_dir=working_dir,
                    agent_id=agent_id,
                    user_context=user_context,
                    conversation_id=(
                        str(effective_conv_id) if effective_conv_id else None
                    ),
                )
                if new_files:
                    response = _inject_file_markers(response, new_files)
                    files_data = [
                        {
                            "file_id": f.file_id,
                            "filename": f.filename,
                            "file_type": f.file_type,
                        }
                        for f in new_files
                    ]

            # ----------------------------------------------------------------
            # 12. Parse response with output parser
            # ----------------------------------------------------------------
            parsed_response = parse_agent_response(response, agent)

            # ----------------------------------------------------------------
            # 13. Update request count + touch session
            # ----------------------------------------------------------------
            self.execution_service._update_request_count(agent, effective_db)

            if session:
                await self.session_service.touch_session(session.id)

            # ----------------------------------------------------------------
            # 14. Update conversation message count
            # ----------------------------------------------------------------
            if conversation:
                from services.conversation_service import ConversationService  # already imported above; safe to re-import

                if isinstance(parsed_response, list):
                    try:
                        text_parts = [
                            item.get("text", "")
                            for item in parsed_response
                            if isinstance(item, dict) and item.get("type") == "text"
                        ]
                        last_message_preview = " ".join(text_parts)[:200]
                    except Exception:
                        last_message_preview = str(parsed_response)[:200]
                else:
                    last_message_preview = (
                        parsed_response[:200]
                        if isinstance(parsed_response, str)
                        else str(parsed_response)[:200]
                    )

                last_message_preview = re.sub(
                    r"!\[[^\]]*\]\(file://[^\)]*\)", "[imagen]", last_message_preview
                )
                last_message_preview = re.sub(
                    r"\[📎[^\]]*\]\(file://[^\)]*\)",
                    "[archivo]",
                    last_message_preview,
                )
                last_message_preview = (
                    last_message_preview.strip() or "[imagen generada]"
                )

                ConversationService.increment_message_count(
                    db=effective_db,
                    conversation_id=conversation.conversation_id,
                    last_message=last_message_preview,
                    increment_by=2,
                )

            # ----------------------------------------------------------------
            # 15. Emit done event
            # ----------------------------------------------------------------
            yield format_sse_event(
                "done",
                {
                    "response": parsed_response,
                    "conversation_id": effective_conv_id,
                    "files": files_data,
                },
            )

        except Exception as exc:
            logger.error("Error in streaming agent chat: %s", str(exc), exc_info=True)
            yield format_sse_event("error", {"message": str(exc)})

        finally:
            if mcp_client:
                logger.info("MCP client will be cleaned up automatically")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_message_payload(
        self,
        agent: Agent,
        message: str,
        image_files: List[Dict[str, Any]],
        user_context: dict | None,
    ) -> HumanMessage:
        """Build the HumanMessage that will be fed into the agent chain.

        When ``image_files`` is non-empty the content becomes a multimodal list
        of text + image_url blocks.  Images are served via a signed URL when
        ``AICT_BASE_URL`` is set (production), or inlined as base64 data URIs in
        development mode.

        Args:
            agent: The (freshly loaded) Agent ORM instance.
            message: The already-enhanced text message (with file content
                appended if applicable).
            image_files: List of image-file dicts (``file_path`` key required).
            user_context: Caller context dict used to generate signed URLs.

        Returns:
            A ``HumanMessage`` instance ready for ``agent_chain.astream()``.
        """
        formatted_message = agent.prompt_template.format(question=message)

        if not image_files:
            return HumanMessage(content=formatted_message)

        app_config = get_app_config()
        tmp_base_folder = app_config["TMP_BASE_FOLDER"]
        aict_base_url = os.getenv("AICT_BASE_URL")

        content: List[Dict[str, Any]] = [
            {"type": "text", "text": formatted_message}
        ]

        for img in image_files:
            file_path: str = img.get("file_path", "")
            if not file_path:
                logger.warning("Image file has no file_path — skipping: %s", img)
                continue

            # Normalise to forward slashes and strip leading slash
            file_path = file_path.replace("\\", "/").lstrip("/")

            if aict_base_url:
                # Production mode — generate a signed static URL
                aict_base_url = aict_base_url.rstrip("/")
                user_email: str | None = (
                    user_context.get("email") if user_context else None
                )
                if user_email:
                    from utils.security import generate_signature

                    sig = generate_signature(file_path, user_email)
                    url = (
                        f"{aict_base_url}/static/{file_path}"
                        f"?user={user_email}&sig={sig}"
                    )
                else:
                    url = f"{aict_base_url}/static/{file_path}"

                logger.info("Adding image to message using signed URL: %s", url)
                content.append(
                    {"type": "image_url", "image_url": {"url": url}}
                )
            else:
                # Development mode — inline as base64 data URI
                full_path = os.path.join(tmp_base_folder, file_path)
                if os.path.exists(full_path):
                    try:
                        mime_type, _ = mimetypes.guess_type(full_path)
                        if not mime_type:
                            mime_type = "image/jpeg"
                        with open(full_path, "rb") as fh:
                            encoded = base64.b64encode(fh.read()).decode("utf-8")
                        data_url = f"data:{mime_type};base64,{encoded}"
                        logger.info(
                            "Adding image as base64 (length: %d)", len(encoded)
                        )
                        content.append(
                            {"type": "image_url", "image_url": {"url": data_url}}
                        )
                    except Exception as exc:
                        logger.error(
                            "Error encoding image as base64: %s — falling back to URL",
                            exc,
                        )
                        url = f"http://localhost:8000/static/{file_path}"
                        content.append(
                            {"type": "image_url", "image_url": {"url": url}}
                        )
                else:
                    url = f"http://localhost:8000/static/{file_path}"
                    logger.warning(
                        "Image not found at %s — falling back to URL: %s",
                        full_path,
                        url,
                    )
                    content.append(
                        {"type": "image_url", "image_url": {"url": url}}
                    )

        return HumanMessage(content=content)
