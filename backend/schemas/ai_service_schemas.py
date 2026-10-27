from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime

from schemas.service_lifecycle_schemas import ServiceLifecycleFieldsMixin


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
    # Last provider failure needing action on the service (rejected key, quota); None when healthy
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None

    # End-of-service lifecycle (status is computed at read time)
    end_of_service_at: Optional[datetime] = None
    deprecation_notice: Optional[str] = None
    auto_move_to_service_id: Optional[int] = None
    lifecycle_status: Literal["active", "deprecated", "retired"] = "active"

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
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None

    # End-of-service lifecycle (status is computed at read time)
    end_of_service_at: Optional[datetime] = None
    deprecation_notice: Optional[str] = None
    auto_move_to_service_id: Optional[int] = None
    lifecycle_status: Literal["active", "deprecated", "retired"] = "active"

    model_config = ConfigDict(from_attributes=True)


class CreateUpdateAIServiceSchema(ServiceLifecycleFieldsMixin):
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
    auto_move_to_service_id: Optional[int] = None
    @field_validator("api_key", "base_url", "aws_access_key_id", "aws_region", mode="before")
    @classmethod
    def _strip_credentials(cls, v):
        # Trim whitespace/newlines that often sneak in when pasting from
        # emails, .env files, or password managers. Keys with trailing
        # whitespace cause httpx to fail building the Authorization header
        # and the OpenAI SDK reports it as a misleading "Connection error".
        return v.strip() if isinstance(v, str) else v
