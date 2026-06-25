"""Unit tests for utils.local_auth_tokens.

Covers:
- Token round-trip (mint → decode)
- Token isolation: DEV_ISSUER tokens are rejected (AC-5)
- Token isolation: OIDC-style tokens are rejected (AC-5)
- Expired token rejection
- Tampered signature rejection
- decode_access_token rejects wrong audience

No database required.  SECRET_KEY is set via os.environ before any import.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

# Provide minimum env vars before importing any backend module.
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only-32chars!")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
os.environ.setdefault("LOCAL_ACCESS_TTL_MINUTES", "15")
os.environ.setdefault("LOCAL_TOKEN_LEEWAY_SECONDS", "0")  # no leeway in tests for precise control

from utils.local_auth_tokens import (
    _ALGORITHM,
    _AUDIENCE,
    _ISSUER,
    decode_access_token,
    mint_access_token,
)
from utils.secret_key import get_secret_key

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ID = 42
_EMAIL = "alice@example.com"
_NAME = "Alice"

DEV_ISSUER = "ia-core-tools-dev"
DEV_AUDIENCE = "ia-core-tools-api"
OIDC_ISSUER = "https://login.microsoftonline.com/tenant/v2.0"


def _mint_with_issuer(issuer: str, audience: str, exp_delta_seconds: int = 900) -> str:
    """Mint an arbitrary JWT signed with the same secret but a custom issuer/audience."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(_USER_ID),
        "email": _EMAIL,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + timedelta(seconds=exp_delta_seconds),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, get_secret_key(), algorithm=_ALGORITHM)


# ---------------------------------------------------------------------------
# mint_access_token / decode_access_token round-trip
# ---------------------------------------------------------------------------


class TestMintAndDecode:
    def test_valid_token_decodes_successfully(self):
        token, expires_at = mint_access_token(_USER_ID, _EMAIL, _NAME)
        claims = decode_access_token(token)

        assert claims["sub"] == str(_USER_ID)
        assert claims["email"] == _EMAIL
        assert claims["name"] == _NAME
        assert claims["iss"] == _ISSUER
        assert claims["aud"] == _AUDIENCE

    def test_expires_at_is_utc_aware(self):
        _, expires_at = mint_access_token(_USER_ID, _EMAIL, _NAME)
        assert expires_at.tzinfo is not None
        assert expires_at.tzinfo == timezone.utc

    def test_expires_at_is_approx_15_minutes_from_now(self):
        before = datetime.now(timezone.utc)
        _, expires_at = mint_access_token(_USER_ID, _EMAIL, _NAME)
        after = datetime.now(timezone.utc)

        # Env var is 15 minutes; allow 5-second slop
        assert before + timedelta(minutes=14, seconds=55) <= expires_at <= after + timedelta(minutes=15, seconds=5)

    def test_name_falls_back_to_email_when_none(self):
        token, _ = mint_access_token(_USER_ID, _EMAIL, None)
        claims = decode_access_token(token)
        assert claims["name"] == _EMAIL

    def test_each_token_has_unique_jti(self):
        t1, _ = mint_access_token(_USER_ID, _EMAIL, _NAME)
        t2, _ = mint_access_token(_USER_ID, _EMAIL, _NAME)
        c1 = decode_access_token(t1)
        c2 = decode_access_token(t2)
        assert c1["jti"] != c2["jti"]


# ---------------------------------------------------------------------------
# Token isolation — AC-5
# ---------------------------------------------------------------------------


class TestTokenIsolation:
    """A LOCAL decode must reject tokens from any other issuer/audience."""

    def test_dev_issuer_token_is_rejected(self):
        """Token carrying a legacy DEV_ISSUER must not pass LOCAL validation."""
        token = _mint_with_issuer(DEV_ISSUER, DEV_AUDIENCE)
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token)

    def test_wrong_audience_same_issuer_is_rejected(self):
        """Token with LOCAL issuer but wrong audience is rejected."""
        token = _mint_with_issuer(_ISSUER, "some-other-audience")
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token)

    def test_oidc_style_token_is_rejected(self):
        """Token from an OIDC provider (different issuer + audience) is rejected."""
        token = _mint_with_issuer(OIDC_ISSUER, "api://my-client-id")
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token)

    def test_dev_audience_correct_issuer_is_rejected(self):
        """Even if someone tries LOCAL issuer with DEV audience, it is rejected."""
        token = _mint_with_issuer(_ISSUER, DEV_AUDIENCE)
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token)

    def test_tampered_signature_is_rejected(self):
        """A valid LOCAL token with a corrupted signature is rejected."""
        token, _ = mint_access_token(_USER_ID, _EMAIL, _NAME)
        tampered = token[:-4] + "XXXX"
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(tampered)

    def test_expired_token_raises_expired_signature_error(self):
        """An expired LOCAL token raises ExpiredSignatureError specifically."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(_USER_ID),
            "email": _EMAIL,
            "name": _NAME,
            "iss": _ISSUER,
            "aud": _AUDIENCE,
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "jti": uuid.uuid4().hex,
        }
        expired_token = jwt.encode(payload, get_secret_key(), algorithm=_ALGORITHM)
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(expired_token)
