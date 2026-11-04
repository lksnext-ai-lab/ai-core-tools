"""
Origin validation dependency for public API endpoints.
Enforces per-app CORS origin restrictions based on app configuration.
"""
from fastapi import HTTPException, Depends, Request, status
from sqlalchemy.orm import Session
from typing import Optional, Protocol

from models.app import App
from db.database import get_db
from services.origins_service import origins_service
from utils.logger import get_logger

logger = get_logger(__name__)


class _CorsScopedApp(Protocol):
    """What `check_allowed_origin` reads off an app: satisfied by `App` and by
    lightweight snapshots that carry just these two fields."""

    app_id: int
    agent_cors_origins: Optional[str]


def check_allowed_origin(app: _CorsScopedApp, origin: Optional[str], app_ref: Optional[str] = None) -> None:
    """
    Validate a request `Origin` header against an already-loaded app's CORS allow-list.

    This is the reusable, **fail-closed** body of `enforce_allowed_origins`, extracted
    so callers that already hold a loaded `App` (e.g. the A2A router, which resolves
    visibility before any limiter runs) can apply the same origin check without a
    second DB lookup. Unlike `enforce_allowed_origins` itself (which, by existing
    public-API convention, is fail-open: a DB or lookup error logs and lets the
    request through), this helper raises straight through on a disallowed origin —
    callers decide whether to wrap it.

    Args:
        app: The already-loaded App whose `agent_cors_origins` allow-list applies.
        origin: The value of the request's `Origin` header, or `None` if absent.
        app_ref: The original app reference from the URL path (id or slug), used only
            for the `X-App-ID` header on the 403 response so the wire contract is
            byte-identical to the original dependency. Defaults to `str(app.app_id)`
            when not given.

    Raises:
        HTTPException: 403 if the origin is not allowed.
    """
    validation_result = origins_service.validate_origin(
        origin=origin or "",
        allowed_origins=app.agent_cors_origins or ""
    )

    if not validation_result.is_allowed:
        logger.warning(f"Origin not allowed for app {app.app_id}. Allowed origins: {app.agent_cors_origins}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=validation_result.error_message or f"Origin '{origin}' is not allowed. Contact the application administrator to add your domain to the allowed origins list.",
            headers={
                "X-CORS-Error": "Origin not allowed",
                "X-App-ID": app_ref or str(app.app_id),
                "X-Origin-Received": origin or "none"
            }
        )


def enforce_allowed_origins(
    app_id: str,
    request: Request,
    db: Session = Depends(get_db)
) -> None:
    """
    FastAPI dependency to enforce allowed origins for per-app CORS validation.

    This dependency is **fail-open** by existing public-API convention: an
    unexpected error (e.g. a DB lookup failure) is logged and the request proceeds
    without origin validation, rather than blocking traffic on an infrastructure
    hiccup. `check_allowed_origin` itself (the extracted body) is fail-closed; the
    try/except here is what makes the overall dependency fail-open.

    Args:
        app_id: The app identifier from the URL path (integer ID or slug)
        request: FastAPI request object to check origin header
        db: Database session

    Raises:
        HTTPException: 403 if origin is not allowed
    """
    try:
        # Load app to get allowed origins (supports both integer ID and slug)
        if app_id.isdigit():
            app = db.query(App).filter(App.app_id == int(app_id)).first()
        else:
            app = db.query(App).filter(App.slug == app_id).first()
        if not app:
            logger.warning(f"App {app_id} not found for origin validation")
            return

        # Get the origin from the request headers
        origin = request.headers.get("origin")

        check_allowed_origin(app, origin, app_ref=app_id)

    except HTTPException:
        # Re-raise HTTP exceptions (like 403)
        raise
    except Exception:
        # Log other errors but don't block the request (fail-open, see docstring)
        logger.exception(f"Error in origin validation for app {app_id}")
        # Continue without origin validation on errors