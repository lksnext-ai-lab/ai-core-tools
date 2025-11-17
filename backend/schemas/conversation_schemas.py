from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class ConversationBase(BaseModel):
    """Base schema for conversation"""
    title: Optional[str] = None


class ConversationCreate(ConversationBase):
    """Schema for creating a new conversation"""
    agent_id: int


class ConversationUpdate(BaseModel):
    """Schema for updating a conversation"""
    title: Optional[str] = None
    last_message: Optional[str] = None
    message_count: Optional[int] = None


class ConversationResponse(ConversationBase):
    """Schema for conversation response"""
    conversation_id: int
    agent_id: int
    user_id: Optional[int] = None
    session_id: str
    created_at: datetime
    updated_at: datetime
    last_message: Optional[str] = None
    message_count: int
    
    model_config = ConfigDict(from_attributes=True)


class ConversationListResponse(BaseModel):
    """Schema for listing conversations"""
    conversations: list[ConversationResponse]
    total: int


class ConversationWithHistoryResponse(ConversationResponse):
    """Schema for conversation with message history"""
    messages: list[dict] = []  # List of {role: str, content: str}

