import json
import math
import os
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form, status
from utils.security import generate_signature

from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Annotated

from db.database import get_db
from routers.internal.auth_utils import get_current_user_oauth
from services.marketplace_service import MarketplaceService
from services.conversation_service import ConversationService
from services.agent_execution_service import AgentExecutionService
from services.agent_service import AgentService
from services.user_service import UserService
from services.file_management_service import FileManagementService, FileReference
from services.marketplace_quota_service import MarketplaceQuotaService
from services.system_settings_service import SystemSettingsService
from utils.config import is_omniadmin
from models.conversation import Conversation, ConversationSource
from models.agent import Agent, MarketplaceVisibility
from schemas.marketplace_schemas import (
    MARKETPLACE_CATEGORIES,
    MarketplaceCatalogResponseSchema,
    MarketplaceAgentDetailSchema,
    MarketplaceConversationListSchema,
    AgentRatingInputSchema,
    AgentRatingResponseSchema,
    UserRatingResponseSchema,
)
from schemas.conversation_schemas import ConversationResponse, ConversationWithHistoryResponse
from schemas.chat_schemas import ChatResponseSchema
from utils.logger import get_logger

logger = get_logger(__name__)

marketplace_router = APIRouter(prefix="/marketplace", tags=["Marketplace"])

CONVERSATION_NOT_FOUND = "Conversation not found"
AGENT_NOT_FOUND = "Agent not found"


def _auth_context_to_dict(auth_context: AuthContext) -> Dict:
    """Convert AuthContext to user_context dict for service layer"""
    return {
        "user_id": int(auth_context.identity.id),
        "email": auth_context.identity.email,
        "oauth": True,
    }


# ==================== QUOTA USAGE ====================


@marketplace_router.get(
    "/quota-usage",
    summary="Get current user's marketplace quota usage",
)
async def get_marketplace_quota_usage(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
) -> dict:
    """Get current user's marketplace quota usage for the current UTC month."""
    user_id = int(current_user.identity.id)
    is_exempt = is_omniadmin(current_user.identity.email)
    call_count = MarketplaceQuotaService.get_current_month_usage(user_id, db)
    settings_service = SystemSettingsService(db)
    quota_value = settings_service.get_setting("marketplace_call_quota")
    quota = int(quota_value) if quota_value is not None else 0
    return {
        "call_count": call_count,
        "quota": quota,
        "is_exempt": is_exempt,
    }


# ==================== CATALOG ====================


@marketplace_router.get(
    "/categories",
    summary="List marketplace categories",
)
async def list_categories(
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
):
    """Return the predefined list of marketplace categories."""
    return {"categories": MARKETPLACE_CATEGORIES}


@marketplace_router.get(
    "/agents",
    summary="Marketplace catalog",
    response_model=MarketplaceCatalogResponseSchema,
)
async def marketplace_catalog(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Annotated[str, Query()] = "relevance",
    search: Optional[str] = None,
    category: Optional[str] = None,
    my_apps_only: bool = False,
):
    """Browse published agents in the marketplace."""
    user_id = int(current_user.identity.id)

    agents, total = MarketplaceService.get_marketplace_catalog(
        db=db,
        user_id=user_id,
        search=search,
        category=category,
        my_apps_only=my_apps_only,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
    )

    return MarketplaceCatalogResponseSchema(
        agents=agents,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@marketplace_router.get(
    "/agents/{agent_id}",
    summary="Marketplace agent detail",
    response_model=MarketplaceAgentDetailSchema,
)
async def marketplace_agent_detail(
    agent_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
):
    """Get full detail for a published marketplace agent."""
    user_id = int(current_user.identity.id)

    detail = MarketplaceService.get_marketplace_agent_detail(db, agent_id, user_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found or not available",
        )
    return detail


# ==================== RATINGS ====================


@marketplace_router.post(
    "/agents/{agent_id}/rate",
    summary="Rate a marketplace agent",
    response_model=AgentRatingResponseSchema,
)
async def rate_marketplace_agent(
    agent_id: int,
    body: AgentRatingInputSchema,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
):
    """
    Submit or update a star rating (1–5) for a published marketplace agent.
    The user must have had at least one conversation with the agent.
    """
    user_id = int(current_user.identity.id)
    try:
        return MarketplaceService.rate_agent(db, agent_id, user_id, body.rating)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@marketplace_router.get(
    "/agents/{agent_id}/my-rating",
    summary="Get current user's rating for an agent",
    response_model=UserRatingResponseSchema,
)
async def get_my_rating(
    agent_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
):
    """Return the authenticated user's current star rating for this agent (null if not rated)."""
    user_id = int(current_user.identity.id)
    return MarketplaceService.get_user_rating(db, agent_id, user_id)


# ==================== CONVERSATIONS ====================


@marketplace_router.post(
    "/agents/{agent_id}/conversations",
    summary="Start marketplace conversation",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_marketplace_conversation(
    agent_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
    title: Optional[str] = None,
):
    """Create a new conversation with a published marketplace agent."""
    user_id = int(current_user.identity.id)
    try:
        conversation = MarketplaceService.create_marketplace_conversation(
            db=db,
            agent_id=agent_id,
            user_id=user_id,
            title=title,
        )
        return conversation
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@marketplace_router.get(
    "/conversations",
    summary="List marketplace conversations",
    response_model=MarketplaceConversationListSchema,
)
async def list_marketplace_conversations(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """List the current user's marketplace conversations."""
    user_id = int(current_user.identity.id)

    conversations, total = MarketplaceService.get_marketplace_conversations(
        db=db,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return MarketplaceConversationListSchema(conversations=conversations, total=total)


@marketplace_router.get(
    "/conversations/{conversation_id}",
    summary="Get marketplace conversation with history",
    response_model=ConversationWithHistoryResponse,
)
async def get_marketplace_conversation(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
):
    """Get a marketplace conversation with its message history."""
    user_context = _auth_context_to_dict(current_user)

    conversation = ConversationService.get_conversation(
        db=db,
        conversation_id=conversation_id,
        user_context=user_context,
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CONVERSATION_NOT_FOUND)

    # Verify conversation is a marketplace conversation
    if getattr(conversation, "source", None) != ConversationSource.MARKETPLACE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CONVERSATION_NOT_FOUND)

    try:
        history = await ConversationService.get_conversation_history(
            db=db,
            conversation_id=conversation_id,
            user_context=user_context,
        )
        return ConversationWithHistoryResponse(
            **conversation.to_dict(),
            messages=history or [],
        )
    except Exception as e:
        logger.error(f"Error retrieving marketplace conversation history: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ==================== FILES ====================


def _get_marketplace_conversation(
    conversation_id: int,
    user_id: int,
    db: Session,
) -> Conversation:
    """Load a marketplace conversation and verify it belongs to the user."""
    conversation = ConversationService.get_marketplace_conversation(
        db=db,
        conversation_id=conversation_id,
        user_id=user_id,
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CONVERSATION_NOT_FOUND)
    return conversation


def _get_agent_or_404(db: Session, agent_id: int) -> Agent:
    """Load agent via service layer and raise 404 when missing."""
    agent_service = AgentService()
    agent = agent_service.get_agent(db=db, agent_id=agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=AGENT_NOT_FOUND)
    return agent


def _build_file_user_context(auth_context: AuthContext, app_id: int) -> Dict:
    return {
        "user_id": int(auth_context.identity.id),
        "email": auth_context.identity.email,
        "oauth": True,
        "app_id": app_id,
    }


@marketplace_router.post(
    "/conversations/{conversation_id}/upload-file",
    summary="Upload file for marketplace conversation",
)
async def upload_marketplace_file(
    conversation_id: int,
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
):
    """Upload and persist a file for a marketplace conversation."""
    user_id = int(current_user.identity.id)
    conversation = _get_marketplace_conversation(conversation_id, user_id, db)
    agent = _get_agent_or_404(db, conversation.agent_id)

    user_context = _build_file_user_context(current_user, agent.app_id)
    file_service = FileManagementService()
    try:
        file_ref = await file_service.upload_file(
            file=file,
            agent_id=agent.agent_id,
            user_context=user_context,
            conversation_id=conversation_id,
        )
        return {
            "success": True,
            "file_id": file_ref.file_id,
            "filename": file_ref.filename,
            "file_type": file_ref.file_type,
            "file_size_bytes": file_ref.file_size_bytes,
            "file_size_display": FileReference.format_file_size(file_ref.file_size_bytes),
            "processing_status": file_ref.processing_status,
            "content_preview": file_ref.content_preview,
            "has_extractable_content": file_ref.has_extractable_content,
            "mime_type": file_ref.mime_type,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading marketplace file: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="File upload failed")


@marketplace_router.get(
    "/conversations/{conversation_id}/files",
    summary="List files for marketplace conversation",
)
async def list_marketplace_files(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
):
    """List files attached to a marketplace conversation."""
    user_id = int(current_user.identity.id)
    conversation = _get_marketplace_conversation(conversation_id, user_id, db)
    agent = _get_agent_or_404(db, conversation.agent_id)

    user_context = _build_file_user_context(current_user, agent.app_id)
    file_service = FileManagementService()
    try:
        files = await file_service.list_attached_files(
            agent_id=agent.agent_id,
            user_context=user_context,
            conversation_id=str(conversation_id),
        )
        total_size = sum(f.get("file_size_bytes", 0) or 0 for f in files)
        return {
            "files": files,
            "total_size_bytes": total_size,
            "total_size_display": FileReference.format_file_size(total_size),
        }
    except Exception as e:
        logger.error(f"Error listing marketplace files: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list files")


@marketplace_router.delete(
    "/conversations/{conversation_id}/files/{file_id}",
    summary="Remove file from marketplace conversation",
)
async def remove_marketplace_file(
    conversation_id: int,
    file_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
):
    """Remove a file attached to a marketplace conversation."""
    user_id = int(current_user.identity.id)
    conversation = _get_marketplace_conversation(conversation_id, user_id, db)
    agent = _get_agent_or_404(db, conversation.agent_id)

    user_context = _build_file_user_context(current_user, agent.app_id)
    file_service = FileManagementService()
    try:
        success = await file_service.remove_file(
            file_id=file_id,
            agent_id=agent.agent_id,
            user_context=user_context,
            conversation_id=str(conversation_id),
        )
        if success:
            return {"success": True, "message": "File removed successfully"}
        return {"success": False, "message": "File not found or already removed"}
    except Exception as e:
        logger.error(f"Error removing marketplace file: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove file")


@marketplace_router.get(
    "/conversations/{conversation_id}/files/{file_id}/download",
    summary="Download a file from a marketplace conversation",
)
async def download_marketplace_file(
    conversation_id: int,
    file_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
):
    """Download an uploaded or agent-generated file from a marketplace conversation."""
    user_id = int(current_user.identity.id)
    conversation = _get_marketplace_conversation(conversation_id, user_id, db)
    agent = _get_agent_or_404(db, conversation.agent_id)

    user_context = _build_file_user_context(current_user, agent.app_id)
    file_service = FileManagementService()
    try:
        file_data = None
        for try_conv_id in [str(conversation_id), None]:
            files = await file_service.list_attached_files(
                agent_id=agent.agent_id,
                user_context=user_context,
                conversation_id=try_conv_id,
            )
            file_data = next((f for f in files if f.get("file_id") == file_id), None)
            if file_data:
                break
        if not file_data or not file_data.get("file_path"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

        file_path = file_data["file_path"].lstrip("/")
        filename = file_data.get("filename", os.path.basename(file_path))
        user_email = current_user.identity.email

        aict_base_url = os.getenv("AICT_BASE_URL", "").rstrip("/")
        if not aict_base_url:
            aict_base_url = str(request.base_url).rstrip("/")

        sig = generate_signature(file_path, user_email)
        download_url = (
            f"{aict_base_url}/static/{file_path}"
            f"?user={user_email}&sig={sig}"
            f"&filename={filename}"
        )

        return {"download_url": download_url, "filename": filename}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading marketplace file: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="File download failed")


# ==================== CHAT ====================


def _parse_file_references_json(file_references: Optional[str]) -> Optional[list]:
    """Parse the file_references form field from JSON string to list."""
    if not file_references:
        return None
    try:
        parsed = json.loads(file_references)
        return parsed if isinstance(parsed, list) else None
    except json.JSONDecodeError:
        logger.warning("Invalid file_references JSON, ignoring")
        return None


def _extract_jwt_token(request: Request) -> Optional[str]:
    """Extract JWT token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    return None




def _validate_marketplace_agent(agent: Optional[Agent]) -> None:
    """Raise if agent is missing or unpublished."""
    if not agent or agent.marketplace_visibility == MarketplaceVisibility.UNPUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This agent is no longer available in the marketplace",
        )
    if agent.app and agent.app.agent_rate_limit and agent.app.agent_rate_limit > 0:
        if agent.request_count and agent.request_count >= agent.app.agent_rate_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="This agent is temporarily unavailable due to high demand. Please try again later.",
            )


@marketplace_router.post(
    "/conversations/{conversation_id}/chat",
    summary="Chat in marketplace conversation",
    response_model=ChatResponseSchema,
)
async def marketplace_chat(
    conversation_id: int,
    request: Request,
    message: Annotated[str, Form(...)],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user_oauth)],
    files: Annotated[List[UploadFile], File()] = None,
    file_references: Annotated[Optional[str], Form()] = None,
):
    """Send a message in a marketplace conversation."""
    user_id = int(current_user.identity.id)

    # Load conversation and verify ownership + source
    conversation = ConversationService.get_marketplace_conversation(
        db=db,
        conversation_id=conversation_id,
        user_id=user_id,
    )

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=CONVERSATION_NOT_FOUND,
        )

    # Load and validate agent
    agent = _get_agent_or_404(db, conversation.agent_id)
    _validate_marketplace_agent(agent)

    # Marketplace quota enforcement
    user = UserService.get_user_by_id(db, user_id)
    if user and not MarketplaceQuotaService.is_user_exempt(user):
        settings_service = SystemSettingsService(db)
        quota_value = settings_service.get_setting("marketplace_call_quota")
        quota = int(quota_value) if quota_value else 0
        if quota > 0 and MarketplaceQuotaService.check_quota_exceeded(user_id, db, quota):
            current_usage = MarketplaceQuotaService.get_current_month_usage(user_id, db)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Marketplace call quota exceeded for this month. Current usage: {current_usage}/{quota}. Quota resets at the start of next month (UTC).",
            )

    try:
        parsed_refs = _parse_file_references_json(file_references)
        jwt_token = _extract_jwt_token(request)

        user_context = {
            "user_id": user_id,
            "email": current_user.identity.email,
            "oauth": True,
            "app_id": agent.app_id,
            "token": jwt_token,
        }

        all_file_references = await FileManagementService().resolve_chat_files(
            files=files,
            file_reference_ids=parsed_refs,
            agent_id=agent.agent_id,
            user_context=user_context,
            conversation_id=conversation_id,
        )

        execution_service = AgentExecutionService()
        result = await execution_service.execute_agent_chat_with_file_refs(
            agent_id=agent.agent_id,
            message=message,
            file_references=all_file_references,
            search_params=None,
            user_context=user_context,
            conversation_id=conversation_id,
            db=db,
        )

        # Increment usage counter after successful execution
        if user and not MarketplaceQuotaService.is_user_exempt(user):
            try:
                MarketplaceQuotaService.increment_usage(user_id, db)
            except Exception as inc_err:
                logger.error(f"Failed to increment marketplace usage for user {user_id}: {inc_err}")

        logger.info(
            f"Marketplace chat processed for agent {agent.agent_id}, "
            f"conversation {conversation_id}, user {user_id}"
        )
        return ChatResponseSchema(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in marketplace chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
