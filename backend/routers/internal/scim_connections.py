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
    SCIMConnectionUpdate,
    OIDCIdentityLinkCreate,
    OIDCIdentityLinkResponse,
)
from schemas.keycloak_scim_setup_schemas import (
    KeycloakLocalSetupStatus,
    KeycloakReconciliationRequest,
    KeycloakReconciliationResponse,
    KeycloakTargetSetupRequest,
    KeycloakTargetSetupResponse,
)
from services.scim_connection_admin_service import (
    SCIMConnectionConflictError,
    SCIMConnectionNotFoundError,
    SCIMConnectionUpdateConflictError,
    SCIMIdentityLinkTargetNotFoundError,
    scim_connection_admin_service,
)
from services.keycloak_scim_setup_service import (
    KeycloakLocalSetupDisabledError,
    KeycloakTargetSetupError,
    keycloak_scim_setup_service,
)

router = APIRouter(tags=["admin"])


@router.get("/keycloak-local-setup/status", response_model=KeycloakLocalSetupStatus)
async def keycloak_local_setup_status(
    _: Annotated[AuthContext, Depends(require_admin)],
) -> KeycloakLocalSetupStatus:
    """Report whether local-only Keycloak auto-setup is enabled."""
    return KeycloakLocalSetupStatus(
        enabled=keycloak_scim_setup_service.is_enabled()
    )


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


@router.post(
    "/{connection_id}/keycloak-target",
    response_model=KeycloakTargetSetupResponse,
)
async def configure_keycloak_target(
    connection_id: int,
    payload: KeycloakTargetSetupRequest,
    _: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> KeycloakTargetSetupResponse:
    """Create and test a local Keycloak outbound SCIM target."""
    try:
        return await keycloak_scim_setup_service.configure_target(
            db, connection_id, payload
        )
    except KeycloakLocalSetupDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local Keycloak auto-setup is disabled.",
        ) from exc
    except KeycloakTargetSetupError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc


@router.post(
    "/{connection_id}/keycloak-reconciliation/dry-run",
    response_model=KeycloakReconciliationResponse,
)
async def keycloak_reconciliation_dry_run(
    connection_id: int,
    payload: KeycloakReconciliationRequest,
    _: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> KeycloakReconciliationResponse:
    """Run a local Keycloak SCIM reconciliation preview."""
    return await _run_keycloak_reconciliation(
        db, connection_id, payload, dry_run=True
    )


@router.post(
    "/{connection_id}/keycloak-reconciliation/run",
    response_model=KeycloakReconciliationResponse,
)
async def keycloak_reconciliation_run(
    connection_id: int,
    payload: KeycloakReconciliationRequest,
    _: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> KeycloakReconciliationResponse:
    """Run a confirmed local Keycloak SCIM reconciliation."""
    return await _run_keycloak_reconciliation(
        db, connection_id, payload, dry_run=False
    )


async def _run_keycloak_reconciliation(
    db: Session,
    connection_id: int,
    payload: KeycloakReconciliationRequest,
    dry_run: bool,
) -> KeycloakReconciliationResponse:
    try:
        return await keycloak_scim_setup_service.reconcile(
            db, connection_id, payload, dry_run=dry_run
        )
    except KeycloakLocalSetupDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local Keycloak auto-setup is disabled.",
        ) from exc
    except KeycloakTargetSetupError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
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


@router.put("/{connection_id}", response_model=SCIMConnectionDetail)
async def update_connection(
    connection_id: int,
    payload: SCIMConnectionUpdate,
    _: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> SCIMConnectionDetail:
    """Update an administrative SCIM connection."""
    try:
        return await keycloak_scim_setup_service.update_connection(
            db, connection_id, payload
        )
    except KeycloakLocalSetupDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local Keycloak auto-setup is disabled.",
        ) from exc
    except KeycloakTargetSetupError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc
    except SCIMConnectionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SCIM connection not found.",
        ) from exc
    except SCIMConnectionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A SCIM connection with the supplied identifiers already exists.",
        ) from exc
    except SCIMConnectionUpdateConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
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
