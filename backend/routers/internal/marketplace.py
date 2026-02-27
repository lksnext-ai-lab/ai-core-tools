import json
import math
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form, status

from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from typing import List, Optional, Dict

from db.database import get_db
from routers.internal.auth_utils import get_current_user_oauth
from services.marketplace_service import MarketplaceService
from services.conversation_service import ConversationService
from services.agent_execution_service import AgentExecutionService
from services.agent_service import AgentService
from services.file_management_service import FileManagementService, FileReference
from models.conversation import Conversation, ConversationSource
from models.agent import Agent, MarketplaceVisibility
from schemas.marketplace_schemas import (
    MARKETPLACE_CATEGORIES,
    MarketplaceCatalogResponseSchema,
    MarketplaceAgentDetailSchema,
    MarketplaceConversationListSchema,
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


# ==================== CATALOG ====================


@marketplace_router.get(
    "/categories",
    summary="List marketplace categories",
)
async def list_categories(
    current_user: AuthContext = Depends(get_current_user_oauth),
):
    """Return the predefined list of marketplace categories."""
    return {"categories": MARKETPLACE_CATEGORIES}


@marketplace_router.get(
    "/agents",
    summary="Marketplace catalog",
    response_model=MarketplaceCatalogResponseSchema,
)
async def marketplace_catalog(
    search: Optional[str] = None,
    category: Optional[str] = None,
    my_apps_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("relevance"),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth),
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
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth),
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


# ==================== CONVERSATIONS ====================


@marketplace_router.post(
    "/agents/{agent_id}/conversations",
    summary="Start marketplace conversation",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_marketplace_conversation(
    agent_id: int,
    title: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth),
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
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth),
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
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth),
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
    conversation = db.query(Conversation).filter(
        Conversation.conversation_id == conversation_id,
        Conversation.user_id == user_id,
        Conversation.source == ConversationSource.MARKETPLACE,
    ).first()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CONVERSATION_NOT_FOUND)
    return conversation


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
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth),
):
    """Upload and persist a file for a marketplace conversation."""
    user_id = int(current_user.identity.id)
    conversation = _get_marketplace_conversation(conversation_id, user_id, db)
    agent = db.query(Agent).filter(Agent.agent_id == conversation.agent_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=AGENT_NOT_FOUND)

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
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth),
):
    """List files attached to a marketplace conversation."""
    user_id = int(current_user.identity.id)
    conversation = _get_marketplace_conversation(conversation_id, user_id, db)
    agent = db.query(Agent).filter(Agent.agent_id == conversation.agent_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=AGENT_NOT_FOUND)

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
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth),
):
    """Remove a file attached to a marketplace conversation."""
    user_id = int(current_user.identity.id)
    conversation = _get_marketplace_conversation(conversation_id, user_id, db)
    agent = db.query(Agent).filter(Agent.agent_id == conversation.agent_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=AGENT_NOT_FOUND)

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


async def _collect_file_references(
    files: Optional[List[UploadFile]],
    parsed_file_references: Optional[list],
    agent_id: int,
    conversation_id: int,
    user_context: Dict,
) -> List[FileReference]:
    """Upload new files and merge with existing file references."""
    file_service = FileManagementService()
    all_refs: List[FileReference] = []
    uploaded_ids: set = set()

    if files:
        for upload_file in files:
            if upload_file.filename:
                ref = await file_service.upload_file(
                    file=upload_file,
                    agent_id=agent_id,
                    user_context=user_context,
                    conversation_id=conversation_id,
                )
                all_refs.append(ref)
                uploaded_ids.add(ref.file_id)

    existing_files = await file_service.list_attached_files(
        agent_id=agent_id,
        user_context=user_context,
        conversation_id=str(conversation_id),
    )

    if parsed_file_references:
        requested_ids = set(parsed_file_references)
        existing_files = [f for f in existing_files if f["file_id"] in requested_ids]

    for file_data in existing_files:
        if file_data["file_id"] not in uploaded_ids:
            all_refs.append(
                FileReference(
                    file_id=file_data["file_id"],
                    filename=file_data["filename"],
                    file_type=file_data["file_type"],
                    content=file_data["content"],
                    file_path=file_data.get("file_path"),
                )
            )

    return all_refs


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
    message: str = Form(...),
    files: List[UploadFile] = File(None),
    file_references: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth),
):
    """Send a message in a marketplace conversation."""
    user_id = int(current_user.identity.id)

    # Load conversation and verify ownership + source
    conversation = db.query(Conversation).filter(
        Conversation.conversation_id == conversation_id,
        Conversation.user_id == user_id,
        Conversation.source == ConversationSource.MARKETPLACE,
    ).first()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=CONVERSATION_NOT_FOUND,
        )

    # Load and validate agent
    agent = db.query(Agent).filter(Agent.agent_id == conversation.agent_id).first()
    _validate_marketplace_agent(agent)

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

        all_file_references = await _collect_file_references(
            files=files,
            parsed_file_references=parsed_refs,
            agent_id=agent.agent_id,
            conversation_id=conversation_id,
            user_context=user_context,
        )

        execution_service = AgentExecutionService(db)
        result = await execution_service.execute_agent_chat_with_file_refs(
            agent_id=agent.agent_id,
            message=message,
            file_references=all_file_references,
            search_params=None,
            user_context=user_context,
            conversation_id=conversation_id,
            db=db,
        )

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
