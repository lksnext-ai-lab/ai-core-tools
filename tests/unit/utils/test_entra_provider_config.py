import time
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from lks_idprovider_entraid import EntraIDProvider
from utils.provider import DEFAULT_LEEWAY_SECONDS, get_entra_config

TENANT_ID = "11111111-1111-1111-1111-111111111111"
CLIENT_ID = "22222222-2222-2222-2222-222222222222"
SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def entra_env(monkeypatch):
    monkeypatch.setenv("AICT_LOGIN", "OIDC")
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT_ID)
    monkeypatch.setenv("ENTRA_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("ENTRA_TOKEN_TYPE", "ID_TOKEN")
    monkeypatch.delenv("ENTRA_LEEWAY", raising=False)


def _id_token(issued_at: int, lifetime_seconds: int = 3600) -> str:
    claims = {
        "aud": CLIENT_ID,
        "iss": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + lifetime_seconds,
        "sub": "subject",
        "oid": "object-id",
        "tid": TENANT_ID,
        "ver": "2.0",
        "email": "user@example.com",
        "preferred_username": "user@example.com",
    }
    return jwt.encode(claims, SIGNING_KEY, algorithm="RS256", headers={"kid": "test-key"})


def _provider() -> EntraIDProvider:
    provider = EntraIDProvider(get_entra_config())
    signing_key = MagicMock()
    signing_key.key = SIGNING_KEY.public_key()
    provider._jwks_client = MagicMock()
    provider._jwks_client.get_signing_key_from_jwt.return_value = signing_key
    return provider


class TestEntraLeewayConfig:
    def test_defaults_to_microsoft_clock_skew(self):
        assert DEFAULT_LEEWAY_SECONDS == 300
        assert get_entra_config().leeway == DEFAULT_LEEWAY_SECONDS

    def test_env_var_overrides_default(self, monkeypatch):
        monkeypatch.setenv("ENTRA_LEEWAY", "60")
        assert get_entra_config().leeway == 60

    def test_out_of_range_value_fails_at_startup(self, monkeypatch):
        monkeypatch.setenv("ENTRA_LEEWAY", "301")
        with pytest.raises(ValidationError):
            get_entra_config()


class TestEntraTokenClockSkew:
    async def test_token_issued_ahead_of_server_clock_is_accepted(self):
        token = _id_token(issued_at=int(time.time()) + 30)
        result = await _provider().validate_token(token)
        assert result.is_valid

    async def test_token_issued_beyond_leeway_is_rejected(self):
        token = _id_token(issued_at=int(time.time()) + DEFAULT_LEEWAY_SECONDS + 60)
        with pytest.raises(Exception, match="not yet valid"):
            await _provider().validate_token(token)

    async def test_expired_token_beyond_leeway_is_rejected(self):
        token = _id_token(issued_at=int(time.time()) - 3600 - DEFAULT_LEEWAY_SECONDS - 60)
        result = await _provider().validate_token(token)
        assert not result.is_valid
        assert "expired" in result.error.lower()
