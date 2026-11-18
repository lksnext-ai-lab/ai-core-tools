"""An unavailable database must answer 503, never 401: a 401 ends the user's session.

Regression for the 2026-10-21 mattin-pro incident, where Postgres ran out of
connection slots and every authenticated request was answered with a 401.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from routers.internal import auth_utils
from routers.internal.auth_utils import (
    AUTH_FAILED_MESSAGE,
    get_current_user_local,
    get_current_user_oauth,
    get_current_user_oidc,
    get_oidc_auth_context,
)

NO_SLOTS = "FATAL:  remaining connection slots are reserved for non-replication superuser connections"


def _no_connection_slots(*_args, **_kwargs):
    raise OperationalError("SELECT users", {}, Exception(NO_SLOTS))


def _oidc_auth_context(email: str = "user@example.com"):
    return SimpleNamespace(
        identity=SimpleNamespace(email=email, name="User", username=email, first_name=None, last_name=None),
        token_info=SimpleNamespace(subject="entra-subject"),
    )


class TestOidcTokenValidation:
    async def test_rejected_token_returns_generic_401_without_the_internal_reason(self):
        provider = MagicMock()
        provider.get_auth_context = AsyncMock(
            side_effect=Exception("Error validating token: The token is not yet valid (iat)")
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_oidc_auth_context(token="token", provider=provider)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == AUTH_FAILED_MESSAGE
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    async def test_valid_token_returns_the_provider_auth_context(self):
        auth_context = _oidc_auth_context()
        provider = MagicMock()
        provider.get_auth_context = AsyncMock(return_value=auth_context)

        assert await get_oidc_auth_context(token="token", provider=provider) is auth_context


class TestOidcUserLookup:
    def test_database_error_propagates_instead_of_401(self, monkeypatch):
        monkeypatch.setattr(auth_utils.UserService, "get_user_by_email", _no_connection_slots)
        auth_context, db = _oidc_auth_context(), MagicMock()

        with pytest.raises(OperationalError):
            get_current_user_oidc(auth_context=auth_context, db=db)

    def test_unexpected_non_database_error_is_still_401(self, monkeypatch):
        def broken_lookup(*_args, **_kwargs):
            raise ValueError("unexpected")

        monkeypatch.setattr(auth_utils.UserService, "get_user_by_email", broken_lookup)
        auth_context, db = _oidc_auth_context(), MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            get_current_user_oidc(auth_context=auth_context, db=db)

        assert exc_info.value.status_code == 401


class TestLocalUserLookup:
    def test_database_error_propagates_instead_of_401(self, monkeypatch):
        monkeypatch.setattr(auth_utils, "decode_local_access_token", lambda _token: {"email": "user@example.com"})
        monkeypatch.setattr(auth_utils.UserService, "get_user_by_email", _no_connection_slots)
        request, db = MagicMock(), MagicMock()

        with pytest.raises(OperationalError):
            get_current_user_local(request=request, credentials=None, access_token_cookie="local-access-token", db=db)


class TestDatabaseUnavailableResponse:
    @pytest.fixture
    def client(self):
        from main import app

        def user_lookup_without_database():
            _no_connection_slots()

        app.dependency_overrides[get_current_user_oauth] = user_lookup_without_database
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.pop(get_current_user_oauth, None)

    def test_authenticated_request_gets_503_with_retry_after(self, client):
        response = client.get("/internal/me")

        assert response.status_code == 503
        assert response.headers["Retry-After"] == "5"
        assert NO_SLOTS not in response.text
        assert "connection slots" not in response.text
