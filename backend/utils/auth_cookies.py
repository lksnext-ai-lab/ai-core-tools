"""HTTP-only cookie helpers for LOCAL auth mode session transport.

Cookie layout:
- ``access_token``  — httpOnly, SameSite=Lax, Path=/
- ``refresh_token`` — httpOnly, SameSite=Lax, Path=/internal/auth
- ``csrf_token``    — NOT httpOnly, SameSite=Lax, Path=/ (JS must read it)

``Secure`` is enabled by default; set ``AUTH_COOKIE_SECURE=false`` only for
local HTTP development.
"""

import secrets
from typing import Optional

from fastapi import Response

from utils.config import Config
from utils.local_auth_tokens import ACCESS_TTL_MINUTES as _TOKEN_ACCESS_TTL_MINUTES
from utils.logger import get_logger
from services.auth.refresh_service import REFRESH_TTL_DAYS as _SERVICE_REFRESH_TTL_DAYS

logger = get_logger(__name__)

_COOKIE_SECURE: bool = Config.get_bool_env_var("AUTH_COOKIE_SECURE", default=True)

# Cookie max-ages share a single source of truth with the token TTL constants.
_ACCESS_TTL_MINUTES: int = _TOKEN_ACCESS_TTL_MINUTES
_REFRESH_TTL_DAYS: int = _SERVICE_REFRESH_TTL_DAYS

COOKIE_ACCESS_TOKEN = "access_token"
COOKIE_REFRESH_TOKEN = "refresh_token"
COOKIE_CSRF_TOKEN = "csrf_token"

_PATH_ROOT = "/"
_PATH_AUTH = "/internal/auth"

_ACCESS_MAX_AGE: int = _ACCESS_TTL_MINUTES * 60
_REFRESH_MAX_AGE: int = _REFRESH_TTL_DAYS * 24 * 60 * 60


def generate_csrf_token() -> str:
    """Return a URL-safe random CSRF token with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def set_session_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    csrf_token: Optional[str] = None,
) -> None:
    """Attach all three session cookies to an outgoing response.

    ``access_token`` and ``refresh_token`` are httpOnly; ``csrf_token`` is
    readable by JS so the frontend can echo it via ``X-CSRF-Token``. Token
    values are never logged.

    Args:
        response: FastAPI response to attach cookies to.
        access_token: Signed LOCAL access JWT.
        refresh_token: Opaque refresh token wire string.
        csrf_token: CSRF token; generated if ``None``.
    """
    if csrf_token is None:
        csrf_token = generate_csrf_token()

    response.set_cookie(
        key=COOKIE_ACCESS_TOKEN,
        value=access_token,
        max_age=_ACCESS_MAX_AGE,
        path=_PATH_ROOT,
        secure=_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        key=COOKIE_REFRESH_TOKEN,
        value=refresh_token,
        max_age=_REFRESH_MAX_AGE,
        path=_PATH_AUTH,
        secure=_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    # csrf_token must NOT be httpOnly so the frontend JS can read it.
    response.set_cookie(
        key=COOKIE_CSRF_TOKEN,
        value=csrf_token,
        max_age=_REFRESH_MAX_AGE,  # CSRF cookie lives as long as the session
        path=_PATH_ROOT,
        secure=_COOKIE_SECURE,
        httponly=False,
        samesite="lax",
    )
    logger.debug(
        "Session cookies set (secure=%s, access_max_age=%ds, refresh_max_age=%ds)",
        _COOKIE_SECURE,
        _ACCESS_MAX_AGE,
        _REFRESH_MAX_AGE,
    )


def clear_session_cookies(response: Response) -> None:
    """Remove all three session cookies from the client.

    Path attributes must exactly match those used in ``set_session_cookies``
    or the browser will not delete the cookies.

    Args:
        response: FastAPI response to attach the delete directives to.
    """
    response.delete_cookie(
        key=COOKIE_ACCESS_TOKEN,
        path=_PATH_ROOT,
        secure=_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=COOKIE_REFRESH_TOKEN,
        path=_PATH_AUTH,
        secure=_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=COOKIE_CSRF_TOKEN,
        path=_PATH_ROOT,
        secure=_COOKIE_SECURE,
        httponly=False,
        samesite="lax",
    )
    logger.debug("Session cookies cleared")
