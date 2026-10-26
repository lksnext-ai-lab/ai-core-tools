"""Contract tests against the real lks-idprovider libraries.

The rest of the suite runs with AICT_LOGIN=LOCAL and mocks auth, so a breaking
change in lks-idprovider-{api,entraid,fastapi} would go unnoticed. These tests
exercise the real classes the app builds in utils/provider.py and
routers/internal/auth_utils.py. No network, no DB.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from lks_idprovider.models.auth import AuthContext
from lks_idprovider.models.identity import User as LksUser
from lks_idprovider.models.token import TokenInfo
from lks_idprovider_entraid import EntraIDConfig, EntraIDProvider, TokenType
from lks_idprovider_fastapi import get_auth_context
from lks_idprovider_fastapi.dependencies import get_default_provider

from routers.internal.auth_utils import _create_enriched_auth_context
from utils import provider as provider_module


def _oidc_auth_context() -> AuthContext:
    return AuthContext(
        identity=LksUser(
            id="entra-oid",
            username="jane@example.com",
            email="jane@example.com",
            name="Jane Doe",
            first_name="Jane",
            last_name="Doe",
        ),
        roles=[],
        token_expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        refresh_expires_at=None,
        provider="entraid",
        scopes=["openid"],
        token_info=TokenInfo(
            token="t",
            token_type="id_token",
            subject="entra-oid",
            audience="aud",
            issuer="iss",
            scopes=["openid"],
        ),
    )


def test_fastapi_dependencies_are_importable():
    assert callable(get_auth_context)
    assert callable(get_default_provider)


def test_entra_config_and_provider_are_built_from_env(monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", "tenant")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "client")
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ENTRA_TOKEN_TYPE", "ACCESS_TOKEN")
    monkeypatch.setenv("ENTRA_LEEWAY", "5")

    config = provider_module.get_entra_config()

    assert isinstance(config, EntraIDConfig)
    assert config.token_type == TokenType.ACCESS_TOKEN
    assert isinstance(EntraIDProvider(config), EntraIDProvider)


def test_enriched_context_from_oidc_auth_context():
    db_user = SimpleNamespace(user_id=42, name="Jane Doe")

    ctx = _create_enriched_auth_context(
        db_user, "jane@example.com", auth_context=_oidc_auth_context()
    )

    assert ctx.identity.id == "42"
    assert ctx.identity.email == "jane@example.com"
    assert ctx.provider == "entraid"
    assert ctx.token_info.subject == "entra-oid"


def test_enriched_context_for_local_user():
    db_user = SimpleNamespace(user_id=7, name="Local User")

    ctx = _create_enriched_auth_context(db_user, "local@example.com")

    assert ctx.identity.id == "7"
    assert ctx.provider == "local"
    assert ctx.token_info.issuer == "mattin-local-auth"
