"""Tenant scoping for routes nested under ``/apps/{app_id}/repositories/{repository_id}``."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.database import get_db
from routers.controls.role_authorization import AppRole, require_min_role
from services.repository_service import RepositoryService
from utils.logger import get_logger

logger = get_logger(__name__)


def validate_repository_app_ownership(repository_id: int, app_id: int, db: Session) -> None:
    """Raise HTTP 404 if the repository does not exist or does not belong to app_id."""
    repo = RepositoryService.get_repository(repository_id, db)
    if not repo or repo.app_id != app_id:
        if repo:
            logger.warning(
                f"Access violation: repository {repository_id} (app {repo.app_id}) accessed from app {app_id}"
            )
        # Same response for missing and foreign repositories: no oracle on other tenants' ids.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")


def require_repository_in_app(
    app_id: int,
    repository_id: int,
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
) -> None:
    """Route dependency: 404 unless ``repository_id`` belongs to the URL's ``app_id``.

    ``require_min_role("viewer")`` is resolved first (401/403 for non-members) so the 404 is
    never an existence oracle for non-members. Routes needing a stricter role keep their own check.
    """
    validate_repository_app_ownership(repository_id, app_id, db)


def require_repository_in_app_or_new(
    app_id: int,
    repository_id: int,
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
) -> None:
    """Like :func:`require_repository_in_app` but lets ``repository_id == 0`` through.

    Only for ``GET /{repository_id}``, where 0 is the blank "new repository" form.
    """
    if repository_id == 0:
        return
    validate_repository_app_ownership(repository_id, app_id, db)
