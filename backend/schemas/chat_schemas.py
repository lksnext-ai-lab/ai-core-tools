from pydantic import BaseModel
from typing import List, Optional, Union, Dict, Any

# ==================== CHAT SCHEMAS ====================

class ChatRequestSchema(BaseModel):
    """Schema for chat request"""
    message: str
    files: Optional[List[str]] = None  # File IDs
    search_params: Optional[dict] = None


class ChatResponseSchema(BaseModel):
    """Schema for chat response"""
    response: Union[str, dict]  # Can be string or JSON object
    agent_id: int
    metadata: dict


class ResetResponseSchema(BaseModel):
    """Schema for reset response"""
    success: bool
    message: str
