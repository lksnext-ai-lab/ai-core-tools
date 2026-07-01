"""JWT utilities for LOCAL auth mode (email+password login).

Single source of truth for minting and decoding LOCAL-issuer access tokens.
Uses a distinct issuer/audience pair so OIDC tokens and any other issuer are
rejected by ``decode_access_token``.

No FastAPI or SQLAlchemy dependencies — safe to import in unit tests.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt

from utils.logger import get_logger
from utils.secret_key import get_secret_key

logger = get_logger(__name__)

_ALGORITHM = "HS256"

_ISSUER = "mattin-local-auth"
_AUDIENCE = "mattin-internal"

_ACCESS_TTL_MINUTES: int = int(os.getenv("LOCAL_ACCESS_TTL_MINUTES", "15"))
#: Exported so auth_cookies.py can share this value without reading the env var again.
ACCESS_TTL_MINUTES: int = _ACCESS_TTL_MINUTES
_LEEWAY_SECONDS: int = int(os.getenv("LOCAL_TOKEN_LEEWAY_SECONDS", "30"))


def mint_access_token(user_id: int, email: str, name: str | None) -> tuple[str, datetime]:
    """Mint a signed LOCAL access token for a user.

    Args:
        user_id: Numeric primary key of the User record.
        email: User's verified email address.
        name: Display name; falls back to email when None.

    Returns:
        ``(token_string, expires_at)`` where ``expires_at`` is timezone-aware UTC.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=_ACCESS_TTL_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "name": name or email,
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": expires_at,
        "jti": uuid.uuid4().hex,
    }

    token: str = jwt.encode(payload, get_secret_key(), algorithm=_ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and fully validate a LOCAL access token.

    Validates signature, expiry (with configurable clock-skew leeway), issuer,
    and audience. OIDC tokens and DEV-issuer tokens are rejected.

    Args:
        token: Raw JWT string.

    Returns:
        Decoded claims dict.

    Raises:
        jwt.ExpiredSignatureError: When the token's ``exp`` has passed.
        jwt.InvalidTokenError: For any other validation failure.
    """
    return jwt.decode(
        token,
        get_secret_key(),
        algorithms=[_ALGORITHM],
        issuer=_ISSUER,
        audience=_AUDIENCE,
        leeway=timedelta(seconds=_LEEWAY_SECONDS),
    )


def generate_local_auth_token(user_id: int, email: str, name: str | None = None) -> Dict[str, Any]:
    """Build the JSON response payload for a successful LOCAL login.

    Args:
        user_id: Numeric primary key of the User record.
        email: User's verified email address.
        name: Display name; falls back to email when ``None``.

    Returns:
        Dict with ``access_token``, ``expires_at`` (naive ISO-8601 + ``"Z"``),
        and ``token_type`` (``"Bearer"``).
    """
    token, expires_at = mint_access_token(user_id, email, name)
    return {
        "access_token": token,
        "expires_at": expires_at.replace(tzinfo=None).isoformat() + "Z",
        "token_type": "Bearer",
    }
