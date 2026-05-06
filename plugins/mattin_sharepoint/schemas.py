"""Pydantic request/response schemas for the SharePoint plugin."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class SharePointSourceCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    tenant_id: str
    client_id: str
    client_secret: str
    site_id: str
    site_name: Optional[str] = None
    site_url: Optional[str] = None
    drive_id: str
    drive_name: Optional[str] = None
    file_extension_filters: Optional[list[str]] = None
    embedding_service_id: Optional[int] = None
    vector_db_type: str = "PGVECTOR"
    silo_name: str


class SharePointSourceUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    file_extension_filters: Optional[list[str]] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


class TestConnectionRequest(BaseModel):
    tenant_id: str
    client_id: str
    client_secret: str
    site_id: Optional[str] = None
    drive_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class SharePointFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    drive_item_id: str
    name: Optional[str] = None
    path: Optional[str] = None
    web_url: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    last_modified_at: Optional[datetime] = None
    status: str
    last_synced_at: Optional[datetime] = None
    error_message: Optional[str] = None


class SharePointSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    app_id: int
    silo_id: int
    name: str
    description: Optional[str] = None
    tenant_id: str
    client_id: str
    # client_secret is intentionally excluded from all response schemas
    site_id: str
    site_name: Optional[str] = None
    site_url: Optional[str] = None
    drive_id: str
    drive_name: Optional[str] = None
    file_extension_filters: Optional[list[str]] = None
    # last_delta_token is intentionally excluded from all response schemas
    last_synced_at: Optional[datetime] = None
    last_sync_status: str
    last_sync_error: Optional[str] = None
    refresh_interval_minutes: Optional[int] = None
    next_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    file_count: int = 0


class SharePointSourceDetailResponse(SharePointSourceResponse):
    files: list[SharePointFileResponse] = []


class MicrosoftSiteResponse(BaseModel):
    id: str
    name: str
    web_url: str


class MicrosoftDriveResponse(BaseModel):
    id: str
    name: str
    drive_type: Optional[str] = None


class TestConnectionResponse(BaseModel):
    ok: bool
    error: Optional[str] = None


class SyncTriggerResponse(BaseModel):
    message: str
    source_id: int
    status: str
