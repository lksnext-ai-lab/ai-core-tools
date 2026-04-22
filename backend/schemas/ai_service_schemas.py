from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== AI SERVICE SCHEMAS ====================

class AIServiceListItemSchema(BaseModel):
    """Schema for AI service list items"""
    service_id: int
    name: str
    provider: Optional[str] = None
    model_name: str
    supports_video: bool = False
    created_at: Optional[datetime]
    needs_api_key: bool = False
    is_system: bool = False

    model_config = ConfigDict(from_attributes=True)


class AIServiceDetailSchema(BaseModel):
    """Schema for detailed AI service information"""
    service_id: int
    name: str
    provider: Optional[str] = None
    model_name: str
    api_key: str
    base_url: str
    supports_video: bool = False
    created_at: Optional[datetime]
    available_providers: List[Dict[str, Any]]
    needs_api_key: bool = False
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateAIServiceSchema(BaseModel):
    """Schema for creating or updating an AI service"""
    name: str
    provider: str
    model_name: str
    api_key: str
    base_url: Optional[str] = ""
    supports_video: bool = False
