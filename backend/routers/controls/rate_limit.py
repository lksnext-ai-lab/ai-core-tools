"""
Rate limiting dependency for public API endpoints.
Enforces per-app agent execution limits using in-memory counters.
"""
import time

from fastapi import HTTPException, Depends, Response, status
from sqlalchemy.orm import Session
from typing import MutableMapping, Optional

from models.app import App
from db.database import get_db
from services.rate_limit_service import rate_limit_service
from utils.logger import get_logger

logger = get_logger(__name__)


def apply_app_rate_limit(app: App, response_headers: MutableMapping[str, str]) -> None:
    """
    Apply the per-app execution rate limit and set the standard rate-limit headers.

    This is the reusable, **fail-closed** body of `enforce_app_rate_limit`, extracted
    so callers that already hold a loaded `App` (e.g. the A2A router, which resolves
    visibility before any limiter runs) can apply the same budget without a second DB
    lookup. Unlike `enforce_app_rate_limit` itself (which, by existing public-API
    convention, is fail-open: a DB or lookup error logs and lets the request through),
    this helper raises straight through when the budget is exceeded.

    Args:
        app: The already-loaded App whose `agent_rate_limit` budget is being consumed.
        response_headers: A mutable header mapping (e.g. `response.headers`) to receive
            the `X-RateLimit-*` headers.

    Raises:
        HTTPException: 429 if the rate limit is exceeded, with `Retry-After` and
            `X-RateLimit-*` headers.
    """
    rate_limit = app.agent_rate_limit or 0

    # If rate limit is 0 or negative, allow unlimited requests
    if rate_limit <= 0:
        # Set headers to indicate unlimited
        response_headers["X-RateLimit-Limit"] = "0"
        response_headers["X-RateLimit-Remaining"] = "-1"
        response_headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
        return

    # Check and consume rate limit
    state = rate_limit_service.check_and_consume(app.app_id, rate_limit)

    # Set rate limit headers
    response_headers["X-RateLimit-Limit"] = str(state.limit)
    response_headers["X-RateLimit-Remaining"] = str(max(0, state.remaining))
    response_headers["X-RateLimit-Reset"] = str(state.reset_epoch)

    # If rate limit exceeded, raise 429
    if state.exceeded:
        retry_after = state.reset_epoch - int(time.time())
        retry_after = max(1, retry_after)  # At least 1 second

        logger.info(f"Rate limit exceeded for app {app.app_id}: {rate_limit} requests per minute")

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {rate_limit} requests per minute allowed.",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(state.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(state.reset_epoch)
            }
        )

    logger.debug(f"Rate limit check passed for app {app.app_id}: {state.remaining} remaining")


def enforce_app_rate_limit(
    app_id: str,
    response: Response,
    db: Session = Depends(get_db)
) -> None:
    """
    FastAPI dependency to enforce per-app rate limiting.

    This dependency is **fail-open** by existing public-API convention: an
    unexpected error (e.g. a DB lookup failure) is logged and the request proceeds
    without rate limiting, rather than blocking traffic on an infrastructure hiccup.
    `apply_app_rate_limit` itself (the extracted body) is fail-closed; the
    try/except here is what makes the overall dependency fail-open.

    Args:
        app_id: The app identifier from the URL path (integer ID or slug)
        response: FastAPI response object to set headers
        db: Database session

    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    try:
        # Load app to get rate limit (supports both integer ID and slug)
        if app_id.isdigit():
            app = db.query(App).filter(App.app_id == int(app_id)).first()
        else:
            app = db.query(App).filter(App.slug == app_id).first()
        if not app:
            logger.warning(f"App {app_id} not found for rate limiting")
            return

        apply_app_rate_limit(app, response.headers)

    except HTTPException:
        # Re-raise HTTP exceptions (like 429)
        raise
    except Exception:
        # Log other errors but don't block the request (fail-open, see docstring)
        logger.exception(f"Error in rate limiting for app {app_id}")
        # Continue without rate limiting on errors
