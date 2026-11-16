from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

from db.database import get_db
from routers.internal.admin import require_admin
from schemas.scim_connection_schemas import (
    SCIMConnectionCreate,
    SCIMConnectionCredentialResponse,
    SCIMConnectionDetail,
    SCIMConnectionListItem,
    SCIMConnectionStatusResponse,
    OIDCIdentityLinkCreate,
    OIDCIdentityLinkResponse,
)
from services.scim_connection_admin_service import (
    SCIMConnectionConflictError,
    SCIMConnectionNotFoundError,
    SCIMIdentityLinkTargetNotFoundError,
    scim_connection_admin_service,
)

router = APIRouter(tags=["admin"])


@router.get("", response_model=list[SCIMConnectionListItem])
async def list_connections(
    _: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SCIMConnectionListItem]:
    """List administrative SCIM connections without secrets."""
    return await run_in_threadpool(scim_connection_admin_service.list_connections, db)


@router.get("/{connection_id}", response_model=SCIMConnectionDetail)
async def get_connection(
    connection_id: int,
    _: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> SCIMConnectionDetail:
    """Get one administrative SCIM connection without its secret."""
    try:
        return await run_in_threadpool(
            scim_connection_admin_service.get_connection, db, connection_id
        )
    except SCIMConnectionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SCIM connection not found.",
        ) from exc


@router.post(
    "",
    response_model=SCIMConnectionCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_connection(
    payload: SCIMConnectionCreate,
    _: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> SCIMConnectionCredentialResponse:
    """Create a SCIM connection and return its bearer token once."""
    try:
        return await run_in_threadpool(
            scim_connection_admin_service.create_connection, db, payload
        )
    except SCIMConnectionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A SCIM connection with the supplied identifiers already exists.",
        ) from exc


@router.post("/{connection_id}/rotate-token", response_model=SCIMConnectionCredentialResponse)
async def rotate_token(
    connection_id: int,
    _: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> SCIMConnectionCredentialResponse:
    """Rotate a connection bearer token and return the new token once."""
    try:
        return await run_in_threadpool(
            scim_connection_admin_service.rotate_token, db, connection_id
        )
    except SCIMConnectionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SCIM connection not found.",
        ) from exc
    except SCIMConnectionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SCIM connection update conflicted.",
        ) from exc


@router.post("/{connection_id}/activate", response_model=SCIMConnectionStatusResponse)
async def activate_connection(
    connection_id: int,
    _: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> SCIMConnectionStatusResponse:
    """Activate a SCIM connection."""
    return await _set_connection_active(db, connection_id, True)


@router.post("/{connection_id}/deactivate", response_model=SCIMConnectionStatusResponse)
async def deactivate_connection(
    connection_id: int,
    _: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> SCIMConnectionStatusResponse:
    """Deactivate a SCIM connection."""
    return await _set_connection_active(db, connection_id, False)


async def _set_connection_active(
    db: Session, connection_id: int, is_active: bool
) -> SCIMConnectionStatusResponse:
    """Translate status-change service errors into HTTP errors."""
    try:
        return await run_in_threadpool(
            scim_connection_admin_service.set_active,
            db,
            connection_id,
            is_active,
        )
    except SCIMConnectionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SCIM connection not found.",
        ) from exc
    except SCIMConnectionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SCIM connection update conflicted.",
        ) from exc


@router.post(
    "/{connection_id}/oidc-identity-links",
    response_model=OIDCIdentityLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_oidc_identity_link(
    connection_id: int,
    payload: OIDCIdentityLinkCreate,
    _: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> OIDCIdentityLinkResponse:
    """Create an admin-approved mapping used by SCIM upsert reconciliation."""
    try:
        return await run_in_threadpool(
            scim_connection_admin_service.create_oidc_identity_link,
            db,
            connection_id,
            payload,
        )
    except SCIMIdentityLinkTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SCIM connection or local user not found.",
        ) from exc
    except SCIMConnectionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An identity mapping with one of these identifiers already exists.",
        ) from exc
