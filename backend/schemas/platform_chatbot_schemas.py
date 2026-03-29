from pydantic import BaseModel
from typing import Optional


class PlatformChatbotConfigResponse(BaseModel):
    """Response schema for the platform chatbot config endpoint."""
    enabled: bool
    agent_name: Optional[str] = None
    agent_description: Optional[str] = None


class PlatformChatbotChatRequest(BaseModel):
    """Request schema for platform chatbot chat endpoints."""
    message: str
    session_id: str
