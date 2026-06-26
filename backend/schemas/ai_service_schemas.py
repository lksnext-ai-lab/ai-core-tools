from pydantic import BaseModel, ConfigDict, field_validator
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
    created_at: Optional[datetime] = None
    available_providers: List[Dict[str, Any]] = []
    needs_api_key: bool = False
    # AWS Bedrock identifiers (non-secret). Empty for other providers.
    aws_access_key_id: Optional[str] = None
    aws_region: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CreateUpdateAIServiceSchema(BaseModel):
    """Schema for creating or updating an AI service"""
    name: str
    provider: str
    model_name: str
    api_key: str
    base_url: Optional[str] = ""
    supports_video: bool = False
    # AWS Bedrock identifiers (non-secret). The secret access key is sent
    # via ``api_key``; the access key id and region travel here.
    aws_access_key_id: Optional[str] = None
    aws_region: Optional[str] = None

    @field_validator("api_key", "base_url", "aws_access_key_id", "aws_region", mode="before")
    @classmethod
    def _strip_credentials(cls, v):
        # Trim whitespace/newlines that often sneak in when pasting from
        # emails, .env files, or password managers. Keys with trailing
        # whitespace cause httpx to fail building the Authorization header
        # and the OpenAI SDK reports it as a misleading "Connection error".
        return v.strip() if isinstance(v, str) else v
