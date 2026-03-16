from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class SystemAIServiceCreate(BaseModel):
    """Request body for creating a system-level AI Service."""
    name: str
    provider: str
    model: str
    api_key_encrypted: Optional[str] = None  # Stored encrypted; write-only
    is_active: bool = True


class SystemAIServiceRead(BaseModel):
    """Read schema for a system-level AI Service. API key excluded."""
    id: int
    name: str
    provider: str
    model: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SystemAIServiceUpdate(BaseModel):
    """Request body for updating a system-level AI Service."""
    name: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key_encrypted: Optional[str] = None  # Write-only; omit to keep existing key
    is_active: Optional[bool] = None
