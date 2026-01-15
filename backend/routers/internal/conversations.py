
from fastapi import APIRouter, Depends, HTTPException, Query
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from typing import Optional, Dict

from db.database import get_db
from routers.internal.auth_utils import get_current_user_oauth
from services.conversation_service import ConversationService
from schemas.conversation_schemas import (
    ConversationCreate,
    ConversationUpdate,
    ConversationResponse,
    ConversationListResponse,
    ConversationWithHistoryResponse
)
from utils.logger import get_logger

logger = get_logger(__name__)

CONVERSATION_NOT_FOUND = "Conversation not found"

router = APIRouter(prefix="/conversations", tags=["Conversations"])


def _auth_context_to_dict(auth_context: AuthContext) -> Dict:
    """Convert AuthContext to user_context dict for service layer"""
    return {
        "user_id": int(auth_context.identity.id),
        "email": auth_context.identity.email,
        "oauth": True
    }


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    agent_id: int,
    title: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth)
):
    """
    Create a new conversation for an agent
    
    Args:
        agent_id: ID of the agent
        title: Optional title for the conversation
    """
    try:
        user_context = _auth_context_to_dict(current_user)
        
        conversation = ConversationService.create_conversation(
            db=db,
            agent_id=agent_id,
            user_context=user_context,
            title=title
        )
        return conversation
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    agent_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth)
):
    """
    List all conversations for a user with a specific agent
    
    Args:
        agent_id: ID of the agent
        limit: Maximum number of results (1-100)
        offset: Pagination offset
    """
    try:
        user_context = _auth_context_to_dict(current_user)
        
        conversations, total = ConversationService.list_conversations(
            db=db,
            agent_id=agent_id,
            user_context=user_context,
            limit=limit,
            offset=offset
        )
        return ConversationListResponse(
            conversations=conversations,
            total=total
        )
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth)
):
    """
    Get a specific conversation by ID
    
    Args:
        conversation_id: ID of the conversation
    """
    user_context = _auth_context_to_dict(current_user)
    
    conversation = ConversationService.get_conversation(
        db=db,
        conversation_id=conversation_id,
        user_context=user_context
    )
    
    if not conversation:
        raise HTTPException(status_code=404, detail=CONVERSATION_NOT_FOUND)
    return conversation


@router.get("/{conversation_id}/history", response_model=ConversationWithHistoryResponse)
async def get_conversation_with_history(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth)
):
    """
    Get a conversation with its complete message history
    
    Args:
        conversation_id: ID of the conversation
    """
    user_context = _auth_context_to_dict(current_user)
    
    # Get conversation metadata
    conversation = ConversationService.get_conversation(
        db=db,
        conversation_id=conversation_id,
        user_context=user_context
    )
    
    if not conversation:
        raise HTTPException(status_code=404, detail=CONVERSATION_NOT_FOUND)
    # Get message history
    try:
        history = await ConversationService.get_conversation_history(
            db=db,
            conversation_id=conversation_id,
            user_context=user_context
        )
        
        return ConversationWithHistoryResponse(
            **conversation.to_dict(),
            messages=history or []
        )
    except Exception as e:
        logger.error(f"Error retrieving conversation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: int,
    update_data: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth)
):
    """
    Update a conversation (mainly for title updates)
    
    Args:
        conversation_id: ID of the conversation
        update_data: Update data
    """
    user_context = _auth_context_to_dict(current_user)
    
    conversation = ConversationService.update_conversation(
        db=db,
        conversation_id=conversation_id,
        user_context=user_context,
        update_data=update_data
    )
    
    if not conversation:
        raise HTTPException(status_code=404, detail=CONVERSATION_NOT_FOUND)
    return conversation


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user_oauth)
):
    """
    Delete a conversation and its associated chat history
    
    Args:
        conversation_id: ID of the conversation
    """
    user_context = _auth_context_to_dict(current_user)
    
    success = await ConversationService.delete_conversation(
        db=db,
        conversation_id=conversation_id,
        user_context=user_context
    )
    
    if not success:
        raise HTTPException(status_code=404, detail=CONVERSATION_NOT_FOUND)
    return {"message": "Conversation deleted successfully"}

