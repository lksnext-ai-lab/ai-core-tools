"""Unit tests for LOCAL auth router: exception → HTTP status mapping.

These tests do NOT require a database.  They mock the service layer entirely
and verify that domain exceptions are mapped to the correct HTTP status codes
and that no internal error details leak to the client.

The router is instantiated standalone (no full app startup) via
``TestClient(router_app)`` so CSRF is not active in these unit tests —
we are solely testing the exception-to-HTTP mapping.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Minimal app fixture — mount the local_auth router without CSRF middleware
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def local_auth_app():
    """Minimal FastAPI app with only the local_auth router mounted.

    Patches are applied at service import level so the router can be loaded
    without the full app initialisation.
    """
    import os
    os.environ.setdefault("AICT_LOGIN", "LOCAL")
    os.environ.setdefault("AUTH_COOKIE_SECURE", "false")
    os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only-32bytes")

    from routers.internal.local_auth import router as local_auth_router
    from db.database import get_db

    app = FastAPI()
    app.include_router(local_auth_router, prefix="/auth")

    # Override get_db to return a no-op session.
    async def _fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _fake_db

    return app


@pytest.fixture(scope="module")
def local_client(local_auth_app):
    with TestClient(local_auth_app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /auth/login — exception mapping
# ---------------------------------------------------------------------------


class TestLoginExceptionMapping:
    def test_credential_error_maps_to_401(self, local_client):
        """CredentialError → 401 (wrong password or unknown user)."""
        from services.auth.credential_service import CredentialError

        with patch(
            "routers.internal.local_auth.CredentialService.authenticate",
            new_callable=AsyncMock,
            side_effect=CredentialError("bad creds"),
        ):
            resp = local_client.post(
                "/auth/login",
                json={"email": "user@test.com", "password": "SomeP@ss12"},
            )
        assert resp.status_code == 401
        detail = resp.json()["detail"]
        assert "invalid" in detail.lower()
        # No internal info in the response body.
        assert "bad creds" not in detail

    def test_account_locked_maps_to_429(self, local_client):
        """AccountLockedError → 429."""
        from services.auth.credential_service import AccountLockedError

        with patch(
            "routers.internal.local_auth.CredentialService.authenticate",
            new_callable=AsyncMock,
            side_effect=AccountLockedError("locked"),
        ):
            resp = local_client.post(
                "/auth/login",
                json={"email": "user@test.com", "password": "SomeP@ss12"},
            )
        assert resp.status_code == 429

    def test_account_locked_includes_retry_after_header(self, local_client):
        """AccountLockedError → 429 with Retry-After header.

        Finding B fix: the Retry-After header must be present on the lockout
        response, consistent with the throttle 429s that already carry it.
        """
        from datetime import datetime, timedelta, timezone
        from services.auth.credential_service import AccountLockedError

        future_lock = datetime.now(timezone.utc) + timedelta(seconds=90)
        with patch(
            "routers.internal.local_auth.CredentialService.authenticate",
            new_callable=AsyncMock,
            side_effect=AccountLockedError("locked", locked_until=future_lock),
        ):
            resp = local_client.post(
                "/auth/login",
                json={"email": "user@test.com", "password": "SomeP@ss12"},
            )
        assert resp.status_code == 429
        assert "retry-after" in resp.headers, "Retry-After header must be present on lockout 429"
        retry_after = int(resp.headers["retry-after"])
        # Value should be positive and within a generous bound (90 ± 5 s).
        assert 0 < retry_after <= 95, f"Unexpected Retry-After value: {retry_after}"

    def test_account_locked_retry_after_fallback_when_locked_until_none(self, local_client):
        """When AccountLockedError carries no locked_until, Retry-After uses the fallback (60)."""
        from services.auth.credential_service import AccountLockedError

        with patch(
            "routers.internal.local_auth.CredentialService.authenticate",
            new_callable=AsyncMock,
            side_effect=AccountLockedError("locked", locked_until=None),
        ):
            resp = local_client.post(
                "/auth/login",
                json={"email": "user@test.com", "password": "SomeP@ss12"},
            )
        assert resp.status_code == 429
        assert "retry-after" in resp.headers
        assert resp.headers["retry-after"] == "60"

    def test_account_locked_body_does_not_leak_internal_detail(self, local_client):
        """Retry-After is in the header; the body must stay generic (no timing leak)."""
        from datetime import datetime, timedelta, timezone
        from services.auth.credential_service import AccountLockedError

        future_lock = datetime.now(timezone.utc) + timedelta(minutes=3)
        with patch(
            "routers.internal.local_auth.CredentialService.authenticate",
            new_callable=AsyncMock,
            side_effect=AccountLockedError("locked", locked_until=future_lock),
        ):
            resp = local_client.post(
                "/auth/login",
                json={"email": "user@test.com", "password": "SomeP@ss12"},
            )
        assert resp.status_code == 429
        detail = resp.json()["detail"]
        # The body must use the generic constant, not the exception message.
        assert "locked" in detail.lower()
        assert "locked_until" not in detail
        assert "180" not in detail  # no raw second count in the body

    def test_inactive_account_maps_to_403(self, local_client):
        """InactiveAccountError → 403."""
        from services.auth.credential_service import InactiveAccountError

        with patch(
            "routers.internal.local_auth.CredentialService.authenticate",
            new_callable=AsyncMock,
            side_effect=InactiveAccountError("inactive"),
        ):
            resp = local_client.post(
                "/auth/login",
                json={"email": "user@test.com", "password": "SomeP@ss12"},
            )
        assert resp.status_code == 403

    def test_missing_email_returns_422(self, local_client):
        """Missing email field → 422 validation error."""
        resp = local_client.post(
            "/auth/login",
            json={"password": "SomeP@ss12"},
        )
        assert resp.status_code == 422

    def test_no_token_in_success_body(self, local_client):
        """AC-7: access_token and refresh_token must NOT appear in the response body."""
        mock_user = MagicMock()
        mock_user.user_id = 1
        mock_user.email = "user@test.com"
        mock_user.name = "Test"

        with (
            patch(
                "routers.internal.local_auth.CredentialService.authenticate",
                new_callable=AsyncMock,
                return_value=mock_user,
            ),
            patch(
                "routers.internal.local_auth.RefreshService.issue_session",
                return_value=("fake_access_token", "jti.opaque_value", MagicMock()),
            ),
            patch("routers.internal.local_auth.set_session_cookies"),
            patch(
                "routers.internal.local_auth.is_omniadmin",
                return_value=False,
            ),
        ):
            resp = local_client.post(
                "/auth/login",
                json={"email": "user@test.com", "password": "SomeP@ss12"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" not in body
        assert "refresh_token" not in body
        assert body["user_id"] == 1
        assert body["email"] == "user@test.com"


# ---------------------------------------------------------------------------
# POST /auth/set-password — exception mapping
# ---------------------------------------------------------------------------


class TestSetPasswordExceptionMapping:
    def test_invalid_token_maps_to_400(self, local_client):
        """TokenError with 'invalid'/'used' message → 400."""
        from services.auth.credential_service import TokenError

        with patch(
            "routers.internal.local_auth.CredentialService.consume_set_password_token",
            new_callable=AsyncMock,
            side_effect=TokenError("Set-password link is invalid."),
        ):
            resp = local_client.post(
                "/auth/set-password",
                json={"token": "bad_token", "new_password": "ValidP@ss1234"},
            )
        assert resp.status_code == 400

    def test_expired_token_maps_to_401(self, local_client):
        """TokenError with 'expired' message → 401."""
        from services.auth.credential_service import TokenError

        with patch(
            "routers.internal.local_auth.CredentialService.consume_set_password_token",
            new_callable=AsyncMock,
            side_effect=TokenError("Set-password link has expired."),
        ):
            resp = local_client.post(
                "/auth/set-password",
                json={"token": "expired_token", "new_password": "ValidP@ss1234"},
            )
        assert resp.status_code == 401

    def test_weak_password_rejected_by_schema(self, local_client):
        """Schema-level password policy rejects weak passwords → 422."""
        resp = local_client.post(
            "/auth/set-password",
            json={"token": "some_token", "new_password": "password"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/refresh — exception mapping
# ---------------------------------------------------------------------------


class TestRefreshExceptionMapping:
    def test_refresh_token_error_maps_to_401(self, local_client):
        """RefreshTokenError → 401 and cookies are cleared."""
        from services.auth.refresh_service import RefreshTokenError

        local_client.cookies.set("refresh_token", "jti.opaque_value")
        local_client.cookies.set("access_token", "some_access_token")

        with (
            patch(
                "routers.internal.local_auth.RefreshService.rotate",
                side_effect=RefreshTokenError("reuse detected"),
            ),
            patch("routers.internal.local_auth.clear_session_cookies") as mock_clear,
        ):
            resp = local_client.post(
                "/auth/refresh",
                headers={"X-CSRF-Token": "any"},
            )

        assert resp.status_code == 401
        mock_clear.assert_called_once()
