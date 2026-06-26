from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== EMBEDDING SERVICE SCHEMAS ====================

class EmbeddingServiceListItemSchema(BaseModel):
    """Schema for embedding service list items"""
    service_id: int
    name: str
    provider: Optional[str] = None
    model_name: str
    created_at: Optional[datetime] = None
    needs_api_key: bool = False
    is_system: bool = False

    model_config = ConfigDict(from_attributes=True)


class EmbeddingServiceDetailSchema(BaseModel):
    """Schema for detailed embedding service information"""
    service_id: int
    name: str
    provider: Optional[str] = None
    model_name: str
    api_key: str
    base_url: str
    api_version: Optional[str] = None
    created_at: Optional[datetime] = None
    available_providers: List[Dict[str, Any]] = []
    needs_api_key: bool = False
    # AWS Bedrock identifiers (non-secret). Empty for other providers.
    aws_access_key_id: Optional[str] = None
    aws_region: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CreateUpdateEmbeddingServiceSchema(BaseModel):
    """Schema for creating or updating an embedding service"""
    name: str
    provider: str
    model_name: str
    api_key: str
    base_url: Optional[str] = ""
    api_version: Optional[str] = None
    # AWS Bedrock identifiers (non-secret). The secret access key is sent
    # via ``api_key``; the access key id and region travel here.
    aws_access_key_id: Optional[str] = None
    aws_region: Optional[str] = None

    @field_validator("api_key", "base_url", "api_version", "aws_access_key_id", "aws_region", mode="before")
    @classmethod
    def _strip_credentials(cls, v):
        # Trim whitespace/newlines that often sneak in when pasting from
        # emails, .env files, or password managers — see the equivalent
        # validator on CreateUpdateAIServiceSchema for context.
        return v.strip() if isinstance(v, str) else v


class EmbeddingServiceOptionSchema(BaseModel):
    """Lightweight schema for embedding service dropdown options (includes is_system flag)."""
    service_id: int
    name: str
    provider: Optional[str] = None
    is_system: bool = False

    model_config = ConfigDict(from_attributes=True)


class AffectedSiloSchema(BaseModel):
    """A silo affected by deletion of a system embedding service."""
    silo_id: int
    silo_name: str
    app_id: int
    app_name: str


class SystemEmbeddingServiceImpactSchema(BaseModel):
    """Response schema for system embedding service deletion impact check."""
    service_id: int
    service_name: str
    affected_silos_count: int
    affected_apps_count: int
    affected_silos: List[AffectedSiloSchema]
