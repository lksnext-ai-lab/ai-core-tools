"""Tenant-scoping dependencies for ``/apps/{app_id}/domains/{domain_id}/...`` routes.

``require_min_role`` only proves the caller's role on the ``app_id`` in the URL. These
dependencies additionally prove the ``domain_id`` in the URL belongs to that app, so a
member of app A can never reach app B's domain by pairing A's ``app_id`` with B's
``domain_id``.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.database import get_db
from models.domain import Domain
from routers.controls.role_authorization import AppRole, require_min_role

DOMAIN_NOT_FOUND = "Domain not found"


def _assert_domain_in_app(app_id: int, domain_id: int, db: Session) -> None:
    domain_app_id = db.query(Domain.app_id).filter(Domain.domain_id == domain_id).scalar()
    if domain_app_id is None or domain_app_id != app_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=DOMAIN_NOT_FOUND)


def validate_domain_app_ownership(
    app_id: int,
    domain_id: int,
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
) -> None:
    """404 unless the domain exists and belongs to ``app_id``.

    Depends on the viewer role check, which runs first: non-members get 403 whether or
    not the domain exists (no existence oracle).
    """
    _assert_domain_in_app(app_id, domain_id, db)


def validate_domain_app_ownership_allow_new(
    app_id: int,
    domain_id: int,
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
) -> None:
    """Same as :func:`validate_domain_app_ownership` but lets ``domain_id == 0`` through.

    Only for ``GET /{domain_id}``, where 0 means "blank form for a new domain".
    """
    if domain_id == 0:
        return
    _assert_domain_in_app(app_id, domain_id, db)


require_domain_in_app = Depends(validate_domain_app_ownership)
require_domain_in_app_or_new = Depends(validate_domain_app_ownership_allow_new)
