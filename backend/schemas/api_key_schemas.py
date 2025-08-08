from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

# ==================== API KEY SCHEMAS ====================

class APIKeyListItemSchema(BaseModel):
    """Schema for API key list items"""
    key_id: int
    name: str
    is_active: bool
    created_at: Optional[datetime]
    last_used_at: Optional[datetime]
    key_preview: str  # First 8 chars + "..."
    
    model_config = ConfigDict(from_attributes=True)


class APIKeyDetailSchema(BaseModel):
    """Schema for detailed API key information"""
    key_id: int
    name: str
    is_active: bool
    created_at: Optional[datetime]
    last_used_at: Optional[datetime]
    key_preview: str
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateAPIKeySchema(BaseModel):
    """Schema for creating or updating an API key"""
    name: str
    is_active: Optional[bool] = True


class APIKeyCreateResponseSchema(APIKeyDetailSchema):
    """Schema for API key creation response - includes actual key value once"""
    key_value: Optional[str] = None  # Only returned on creation
    message: str
