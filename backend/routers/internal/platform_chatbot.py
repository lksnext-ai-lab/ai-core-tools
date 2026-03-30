from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import Annotated
from sqlalchemy.orm import Session
from lks_idprovider import AuthContext

from db.database import get_db
from routers.internal.auth_utils import get_current_user_oauth
from services.system_settings_service import SystemSettingsService
from services.agent_service import AgentService
from services.agent_execution_service import AgentExecutionService
from services.agent_streaming_service import AgentStreamingService
from schemas.platform_chatbot_schemas import (
    PlatformChatbotConfigResponse,
    PlatformChatbotChatRequest,
)
from schemas.chat_schemas import ChatResponseSchema
from utils.logger import get_logger

logger = get_logger(__name__)

platform_chatbot_router = APIRouter(tags=["Platform Chatbot"])

CHATBOT_NOT_CONFIGURED = "Platform chatbot is not configured"
CHATBOT_AGENT_NOT_FOUND = "Configured chatbot agent not found"


def _get_agent_id(db: Session) -> int | None:
    """Read the configured platform chatbot agent ID from system settings."""
    return SystemSettingsService(db).get_setting("platform_chatbot_agent_id")


@platform_chatbot_router.get(
    "/config",
    response_model=PlatformChatbotConfigResponse,
    summary="Get platform chatbot configuration",
)
async def get_platform_chatbot_config(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
) -> PlatformChatbotConfigResponse:
    """Return whether the platform chatbot is enabled and its display metadata."""
    agent_id = _get_agent_id(db)
    if agent_id is None or agent_id == -1:
        return PlatformChatbotConfigResponse(enabled=False)

    agent = AgentService().get_agent(db=db, agent_id=agent_id)
    if agent is None:
        return PlatformChatbotConfigResponse(enabled=False)

    return PlatformChatbotConfigResponse(
        enabled=True,
        agent_name=agent.name,
        agent_description=agent.description,
    )


@platform_chatbot_router.post(
    "/chat",
    response_model=ChatResponseSchema,
    summary="Send a message to the platform chatbot",
)
async def platform_chatbot_chat(
    body: PlatformChatbotChatRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
) -> ChatResponseSchema:
    """Proxy a chat message to the configured platform chatbot agent."""
    agent_id = _get_agent_id(db)
    if agent_id is None or agent_id == -1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=CHATBOT_NOT_CONFIGURED,
        )

    agent = AgentService().get_agent(db=db, agent_id=agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=CHATBOT_AGENT_NOT_FOUND,
        )

    user_context = {
        "user_id": int(current_user.identity.id),
        "email": current_user.identity.email,
        "oauth": True,
        "app_id": agent.app_id,
    }

    try:
        result = await AgentExecutionService().execute_agent_chat_with_file_refs(
            agent_id=agent.agent_id,
            message=body.message,
            file_references=None,
            search_params=None,
            user_context=user_context,
            conversation_id=None,
            db=db,
        )
        return ChatResponseSchema(**result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Platform chatbot execution error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chatbot temporarily unavailable",
        )


@platform_chatbot_router.post(
    "/chat/stream",
    summary="Stream a message to the platform chatbot via SSE",
)
async def platform_chatbot_chat_stream(
    body: PlatformChatbotChatRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
) -> StreamingResponse:
    """Stream a chat response from the configured platform chatbot agent via SSE."""
    agent_id = _get_agent_id(db)
    if agent_id is None or agent_id == -1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=CHATBOT_NOT_CONFIGURED,
        )

    agent = AgentService().get_agent(db=db, agent_id=agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=CHATBOT_AGENT_NOT_FOUND,
        )

    user_context = {
        "user_id": int(current_user.identity.id),
        "email": current_user.identity.email,
        "oauth": True,
        "app_id": agent.app_id,
    }

    try:
        streaming_service = AgentStreamingService(db)
        generator = streaming_service.stream_agent_chat(
            agent_id=agent.agent_id,
            message=body.message,
            file_references=None,
            search_params=None,
            user_context=user_context,
            conversation_id=None,
            db=db,
        )
        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Platform chatbot streaming error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chatbot temporarily unavailable",
        )
