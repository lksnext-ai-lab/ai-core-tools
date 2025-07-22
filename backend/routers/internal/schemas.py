from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

# ==================== APP SCHEMAS ====================

class AppListItemSchema(BaseModel):
    """Schema for app list items"""
    app_id: int
    name: str
    role: str  # "owner", "admin", "member"
    created_at: Optional[datetime]
    langsmith_configured: bool
    
    model_config = ConfigDict(from_attributes=True)


class AppDetailSchema(BaseModel):
    """Schema for detailed app information"""
    app_id: int
    name: str
    langsmith_api_key: str
    user_role: str
    created_at: Optional[datetime]
    owner_id: int
    
    model_config = ConfigDict(from_attributes=True)


class CreateAppSchema(BaseModel):
    """Schema for creating a new app"""
    name: str
    langsmith_api_key: Optional[str] = ""


class UpdateAppSchema(BaseModel):
    """Schema for updating an app"""
    name: str
    langsmith_api_key: Optional[str] = ""


# ==================== COMMON RESPONSE SCHEMAS ====================

class MessageResponseSchema(BaseModel):
    """Standard message response"""
    message: str


class ErrorResponseSchema(BaseModel):
    """Standard error response"""
    detail: str 