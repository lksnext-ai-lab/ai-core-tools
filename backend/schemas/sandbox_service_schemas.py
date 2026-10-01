from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== SANDBOX SERVICE SCHEMAS ====================

class SandboxServiceListItemSchema(BaseModel):
    """Schema for sandbox service list items"""
    service_id: int
    name: str
    provider: Optional[str] = None
    created_at: Optional[datetime]
    needs_api_key: bool = False
    is_system: bool = False

    model_config = ConfigDict(from_attributes=True)


class SandboxServiceDetailSchema(BaseModel):
    """Schema for detailed sandbox service information"""
    service_id: int
    name: str
    provider: Optional[str] = None
    api_key: str
    base_url: str = ""
    created_at: Optional[datetime] = None
    available_providers: List[Dict[str, Any]] = []
    needs_api_key: bool = False
    # Provider-specific extra_config fields (non-secret). Empty for other providers.
    opensandbox_image: Optional[str] = None
    daytona_target: Optional[str] = None
    daytona_workspace: Optional[str] = None
    daytona_cpu: Optional[int] = None
    daytona_memory_gb: Optional[int] = None
    e2b_template: Optional[str] = None
    e2b_workspace: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CreateUpdateSandboxServiceSchema(BaseModel):
    """Schema for creating or updating a sandbox service"""
    name: str
    provider: str
    api_key: str
    base_url: Optional[str] = ""
    opensandbox_image: Optional[str] = None
    daytona_target: Optional[str] = None
    daytona_workspace: Optional[str] = None
    daytona_cpu: Optional[int] = None
    daytona_memory_gb: Optional[int] = None
    e2b_template: Optional[str] = None
    e2b_workspace: Optional[str] = None

    @field_validator(
        "api_key",
        "base_url",
        "opensandbox_image",
        "daytona_target",
        "daytona_workspace",
        "e2b_template",
        "e2b_workspace",
        mode="before",
    )
    @classmethod
    def _strip_credentials(cls, v):
        # Trim whitespace/newlines that often sneak in when pasting from
        # emails, .env files, or password managers. Keys with trailing
        # whitespace cause httpx to fail building the Authorization header
        # and the SDK reports it as a misleading "Connection error".
        return v.strip() if isinstance(v, str) else v
