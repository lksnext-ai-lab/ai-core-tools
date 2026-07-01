"""CSRF double-submit cookie protection for the internal API.

Implements the double-submit cookie pattern: browser sends ``csrf_token`` cookie
automatically; JS reads it and echoes the value in ``X-CSRF-Token``; this
dependency compares both with a constant-time compare and rejects on mismatch.

Only cookie-authenticated requests (those carrying an ``access_token`` cookie)
are subject to enforcement. Bearer/API-key callers are skipped. Auth-entry
endpoints (login, set-password) are exempt because they re-establish the session
and the old CSRF token is unavailable to a legitimate client.
"""

import hmac
from typing import Optional

from fastapi import Cookie, Header, HTTPException, Request, status

from utils.logger import get_logger

logger = get_logger(__name__)

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Auth-entry endpoints that reset the session; body-carried credentials already
# prevent cross-site abuse via SameSite=Lax.
_CSRF_EXEMPT_SUFFIXES = ("/auth/login", "/auth/set-password")

# Generic message — never reveal whether cookie or header was absent vs. mismatched.
_CSRF_ERROR_MESSAGE = "CSRF validation failed"


async def enforce_csrf(
    request: Request,
    access_token_cookie: Optional[str] = Cookie(default=None, alias="access_token"),
    csrf_cookie: Optional[str] = Cookie(default=None, alias="csrf_token"),
    x_csrf_token: Optional[str] = Header(default=None, alias="X-CSRF-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-KEY"),
) -> None:
    """Enforce CSRF double-submit for cookie-authenticated mutating requests.

    Attach only to the internal router. Raises HTTP 403 when a cookie session
    makes a mutating request without a matching ``X-CSRF-Token`` header.
    """
    if request.method not in _MUTATING_METHODS:
        return

    if request.url.path.endswith(_CSRF_EXEMPT_SUFFIXES):
        return

    if not access_token_cookie:
        return

    if not csrf_cookie or not x_csrf_token:
        logger.warning(
            "CSRF check failed: missing token — method=%s path=%s "
            "has_cookie=%s has_header=%s",
            request.method,
            request.url.path,
            bool(csrf_cookie),
            bool(x_csrf_token),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_CSRF_ERROR_MESSAGE,
        )

    # Constant-time comparison prevents timing attacks.
    tokens_match = hmac.compare_digest(
        csrf_cookie.encode("utf-8"),
        x_csrf_token.encode("utf-8"),
    )
    if not tokens_match:
        logger.warning(
            "CSRF check failed: token mismatch — method=%s path=%s",
            request.method,
            request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_CSRF_ERROR_MESSAGE,
        )

    logger.debug("CSRF check passed — method=%s path=%s", request.method, request.url.path)
