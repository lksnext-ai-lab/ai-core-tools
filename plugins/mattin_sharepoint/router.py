"""SharePoint plugin router — mounts under /internal when the plugin is loaded."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from lks_idprovider.models.auth import AuthContext
from db.database import get_db
from routers.internal.auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole

from mattin_sharepoint.schemas import (
    SharePointSourceCreateRequest,
    SharePointSourceUpdateRequest,
    SharePointSourceResponse,
    SharePointSourceDetailResponse,
    MicrosoftSiteResponse,
    MicrosoftDriveResponse,
    TestConnectionRequest,
    TestConnectionResponse,
    SyncTriggerResponse,
)
from mattin_sharepoint.graph_client import GraphAuthError, GraphAccessError
from mattin_sharepoint.service import SharePointSourceService
from mattin_sharepoint.repository import SharePointSourceRepository
from mattin_sharepoint.worker import enqueue_sync, ConflictError

router = APIRouter(tags=["SharePoint"])


# ============================================================
# SharePoint Sources CRUD — /apps/{app_id}/sharepoint-sources
# ============================================================

@router.get(
    "/apps/{app_id}/sharepoint-sources",
    response_model=list[SharePointSourceResponse],
)
async def list_sharepoint_sources(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """List all SharePoint sources for an app."""
    return SharePointSourceService.list_sources(app_id, db)


@router.post(
    "/apps/{app_id}/sharepoint-sources",
    response_model=SharePointSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sharepoint_source(
    app_id: int,
    data: SharePointSourceCreateRequest,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """Create a new SharePoint source. Tests credentials before creation."""
    return await SharePointSourceService.create_source(app_id, data, db)


@router.get(
    "/apps/{app_id}/sharepoint-sources/{source_id}",
    response_model=SharePointSourceDetailResponse,
)
async def get_sharepoint_source(
    app_id: int,
    source_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """Get a SharePoint source with its file list."""
    return SharePointSourceService.get_source(source_id, app_id, db)


@router.put(
    "/apps/{app_id}/sharepoint-sources/{source_id}",
    response_model=SharePointSourceResponse,
)
async def update_sharepoint_source(
    app_id: int,
    source_id: int,
    data: SharePointSourceUpdateRequest,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """Update a SharePoint source. Validates credentials if they are changed."""
    return await SharePointSourceService.update_source(source_id, app_id, data, db)


@router.delete(
    "/apps/{app_id}/sharepoint-sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_sharepoint_source(
    app_id: int,
    source_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """Delete a SharePoint source, its files, and its linked silo."""
    SharePointSourceService.delete_source(source_id, app_id, db)


@router.post(
    "/apps/{app_id}/sharepoint-sources/{source_id}/sync",
    response_model=SyncTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_sharepoint_sync(
    app_id: int,
    source_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """Enqueue a SharePoint sync run for the given source."""
    from models.enums.sharepoint_sync_status import SharePointSyncStatus
    source = SharePointSourceRepository.get_by_id_and_app(source_id, app_id, db)
    if not source:
        raise HTTPException(status_code=404, detail="SharePoint source not found")
    if source.last_sync_status == SharePointSyncStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Sync already in progress")
    try:
        await enqueue_sync(source_id)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return SyncTriggerResponse(
        message="Sync enqueued",
        source_id=source_id,
        status="QUEUED",
    )


# ============================================================
# Microsoft Graph helpers — /microsoft/...
# ============================================================

@router.get(
    "/microsoft/sites",
    response_model=list[MicrosoftSiteResponse],
)
async def search_microsoft_sites(
    tenant_id: Annotated[str, Query()],
    client_id: Annotated[str, Query()],
    client_secret: Annotated[str, Query()],
    q: Annotated[str, Query()],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
):
    """Search SharePoint sites by keyword using provided credentials."""
    from mattin_sharepoint.graph_client import GraphClient
    try:
        token = await GraphClient.get_token(tenant_id, client_id, client_secret)
        sites = await GraphClient.search_sites(token, q)
    except GraphAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except GraphAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return [
        MicrosoftSiteResponse(
            id=s.get("id", ""),
            name=s.get("displayName") or s.get("name", ""),
            web_url=s.get("webUrl", ""),
        )
        for s in sites
    ]


@router.get(
    "/microsoft/drives",
    response_model=list[MicrosoftDriveResponse],
)
async def list_microsoft_drives(
    tenant_id: Annotated[str, Query()],
    client_id: Annotated[str, Query()],
    client_secret: Annotated[str, Query()],
    site_id: Annotated[str, Query()],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
):
    """List drives for a SharePoint site using provided credentials."""
    from mattin_sharepoint.graph_client import GraphClient
    try:
        token = await GraphClient.get_token(tenant_id, client_id, client_secret)
        drives = await GraphClient.list_drives(token, site_id)
    except GraphAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except GraphAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return [
        MicrosoftDriveResponse(
            id=d.get("id", ""),
            name=d.get("name", ""),
            drive_type=d.get("driveType"),
        )
        for d in drives
    ]


@router.post(
    "/microsoft/test-connection",
    response_model=TestConnectionResponse,
)
async def test_microsoft_connection(
    data: TestConnectionRequest,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
):
    """Test Microsoft Graph credentials and optionally verify drive/site access."""
    try:
        await SharePointSourceService._test_connection(
            data.tenant_id, data.client_id, data.client_secret,
            site_id=data.site_id, drive_id=data.drive_id,
        )
    except GraphAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except GraphAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return TestConnectionResponse(ok=True)
