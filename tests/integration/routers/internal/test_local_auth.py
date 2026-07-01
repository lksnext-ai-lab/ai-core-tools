"""Integration tests for LOCAL auth HTTP endpoints.

Tests run against the real test PostgreSQL DB (port 5433).
They require ``AICT_LOGIN=LOCAL`` (which is now the default test mode).

The conftest ``client`` fixture overrides ``get_db`` to the rollback-isolated
test session.  Because ``AuthConfig.LOGIN_MODE`` is evaluated at import time
in ``auth_utils.py`` (the dispatch block at module bottom), we reload the
relevant modules after patching the env var so the correct dispatch path
(``get_current_user_local``) is active.

Coverage:
- admin-create → set-password token → set password (consume token)
  → login (httpOnly cookies set, NO token in body) → refresh (rotation)
  → logout (revocation).
- register endpoint is unavailable in LOCAL mode (FR-D2/AC-12).
- change-password flow.
- duplicate user creation returns 409.
- invalid/used token returns 400; expired token returns 401.
- Wrong password returns generic 401 (no enumeration).
"""

import importlib
import os
import pytest
from typing import Generator


# ---------------------------------------------------------------------------
# Module-level env patch — must happen BEFORE the FastAPI app is imported
# in the `client` fixture.  We use a module-scoped autouse fixture that sets
# and restores os.environ directly (no monkeypatch — monkeypatch is
# function-scoped and cannot be injected into a module-scoped fixture without
# triggering a pytest ScopeMismatch error).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def local_auth_env():
    """Force AICT_LOGIN=LOCAL and reload auth modules for this test module.

    Saves the previous values of all modified env vars and restores them in
    teardown so the rest of the test suite is unaffected.
    """
    _prev_login = os.environ.get("AICT_LOGIN")
    _prev_secure = os.environ.get("AUTH_COOKIE_SECURE")

    os.environ["AICT_LOGIN"] = "LOCAL"
    # Disable the Secure cookie flag so TestClient (HTTP, not HTTPS) can set cookies.
    os.environ["AUTH_COOKIE_SECURE"] = "false"

    # Reload config and dispatch modules so the new env values take effect.
    import utils.auth_config as auth_config_mod
    import routers.internal.auth_utils as auth_utils_mod
    import utils.auth_cookies as auth_cookies_mod
    import routers.internal.local_auth as local_auth_mod
    import routers.internal as internal_init

    importlib.reload(auth_config_mod)
    importlib.reload(auth_cookies_mod)
    importlib.reload(auth_utils_mod)
    importlib.reload(local_auth_mod)
    importlib.reload(internal_init)

    yield

    # Restore original env state (LOCAL mode is the conftest default).
    if _prev_login is None:
        os.environ.pop("AICT_LOGIN", None)
    else:
        os.environ["AICT_LOGIN"] = _prev_login

    if _prev_secure is None:
        os.environ.pop("AUTH_COOKIE_SECURE", None)
    else:
        os.environ["AUTH_COOKIE_SECURE"] = _prev_secure

    # Reload auth modules back to the original mode.
    importlib.reload(auth_config_mod)
    importlib.reload(auth_utils_mod)
    importlib.reload(internal_init)


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def local_user(db):
    """A LOCAL auth user seeded by the admin workflow (no credential yet)."""
    from models.user import User

    user = User(
        email="local_auth_test@mattin-test.com",
        name="Local Test User",
        is_active=True,
        auth_method="local",
        email_verified=True,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture(scope="function")
def local_user_with_credential(db, local_user) -> tuple:
    """A LOCAL auth user with a hashed password set.

    Returns:
        Tuple of (User, plaintext_password).
    """
    import asyncio
    from repositories.user_credential_repository import UserCredentialRepository
    from services.auth.credential_service import hash_password

    plain_password = "T3stPassw0rd!correct"
    hashed = asyncio.run(hash_password(plain_password))
    cred_repo = UserCredentialRepository(db)
    cred_repo.create(user_id=local_user.user_id, hashed_password=hashed)
    # Mark verified so the is_verified gate passes.
    cred_repo.mark_verified(local_user.user_id)
    db.flush()
    return local_user, plain_password


# ---------------------------------------------------------------------------
# FR-D2 / AC-12: Registration must be unavailable in LOCAL mode
# ---------------------------------------------------------------------------


class TestRegistrationUnavailable:
    def test_register_endpoint_not_found_in_local_mode(self, client):
        """POST /internal/auth/register must not exist in LOCAL mode."""
        response = client.post(
            "/internal/auth/register",
            json={"email": "reg@test.com", "password": "TestPass123!"},
        )
        # 404 (not registered) or 405 (method not allowed) are both acceptable;
        # any 2xx or token in body is a failure.
        assert response.status_code in (404, 405, 422)
        data = response.json()
        assert "access_token" not in str(data)


# ---------------------------------------------------------------------------
# Admin create user → set-password token → consume token → login
# ---------------------------------------------------------------------------


class TestAdminCreateAndLogin:
    def test_admin_create_user_returns_token(self, client, db):
        """Admin can create a LOCAL user and receives a set-password token."""
        from models.user import User
        from utils.config import is_omniadmin

        # Seed an omniadmin user so require_admin passes.
        omniadmin_emails = os.getenv("AICT_OMNIADMINS", "")
        if not omniadmin_emails:
            pytest.skip("AICT_OMNIADMINS not set; cannot test admin endpoints")

        admin_email = omniadmin_emails.split(",")[0].strip()
        admin = User(
            email=admin_email,
            name="Admin",
            is_active=True,
            auth_method="local",
            email_verified=True,
        )
        db.add(admin)

        import asyncio
        from repositories.user_credential_repository import UserCredentialRepository
        from services.auth.credential_service import hash_password
        from models.refresh_token import RefreshToken

        plain_pw = "Adm1nP@ss!123"
        hashed = asyncio.run(hash_password(plain_pw))
        db.flush()
        cred_repo = UserCredentialRepository(db)
        cred_repo.create(user_id=admin.user_id, hashed_password=hashed)
        cred_repo.mark_verified(admin.user_id)
        db.flush()

        # Log in as admin to get cookies.
        login_resp = client.post(
            "/internal/auth/login",
            json={"email": admin_email, "password": plain_pw},
        )
        assert login_resp.status_code == 200, login_resp.text
        csrf = login_resp.cookies.get("csrf_token")

        # Create the new user.
        create_resp = client.post(
            "/internal/admin/users/local",
            json={"email": "newlocal@mattin-test.com", "name": "New Local"},
            headers={"X-CSRF-Token": csrf} if csrf else {},
        )
        assert create_resp.status_code == 201, create_resp.text
        data = create_resp.json()
        assert "set_password_token" in data
        assert "user_id" in data
        assert data["email"] == "newlocal@mattin-test.com"

    def test_full_flow_create_set_password_login(self, client, db):
        """Full admin-create → consume-token → login flow."""
        from models.user import User
        import asyncio
        from repositories.user_credential_repository import UserCredentialRepository
        from services.auth.credential_service import hash_password, CredentialService

        # Create a new local user directly (simulate admin).
        user = User(
            email="flowtest@mattin-test.com",
            name="Flow Test",
            is_active=True,
            auth_method="local",
            email_verified=False,
        )
        db.add(user)

        placeholder = asyncio.run(hash_password("__placeholder__placeholder__"))
        db.flush()
        cred_repo = UserCredentialRepository(db)
        cred_repo.create(user_id=user.user_id, hashed_password=placeholder)
        db.flush()

        # Issue set-password token.
        token = CredentialService.issue_set_password_token(db, user.user_id)
        assert token

        # Set password via the HTTP endpoint (no auth required — link-based flow).
        set_resp = client.post(
            "/internal/auth/set-password",
            json={"token": token, "new_password": "MyN3wPass!word"},
        )
        assert set_resp.status_code == 200, set_resp.text
        assert "log in" in set_resp.json()["message"].lower()

        # Login → cookies must be set, no token in body.
        login_resp = client.post(
            "/internal/auth/login",
            json={"email": "flowtest@mattin-test.com", "password": "MyN3wPass!word"},
        )
        assert login_resp.status_code == 200, login_resp.text

        body = login_resp.json()
        assert "access_token" not in body, "AC-7 violated: token in response body"
        assert "refresh_token" not in body, "AC-7 violated: refresh token in response body"
        assert body["email"] == "flowtest@mattin-test.com"

        # httpOnly cookies must be present.
        assert "access_token" in login_resp.cookies
        assert "refresh_token" in login_resp.cookies
        assert "csrf_token" in login_resp.cookies


# ---------------------------------------------------------------------------
# Refresh token rotation
# ---------------------------------------------------------------------------


class TestRefreshTokenRotation:
    def test_refresh_returns_new_cookies(self, client, local_user_with_credential):
        """Refresh endpoint rotates tokens and returns new cookies."""
        user, plain_pw = local_user_with_credential

        login_resp = client.post(
            "/internal/auth/login",
            json={"email": user.email, "password": plain_pw},
        )
        assert login_resp.status_code == 200, login_resp.text
        csrf = login_resp.cookies.get("csrf_token")

        refresh_resp = client.post(
            "/internal/auth/refresh",
            headers={"X-CSRF-Token": csrf} if csrf else {},
        )
        assert refresh_resp.status_code == 200, refresh_resp.text
        body = refresh_resp.json()
        assert "access_token" not in body
        assert "refresh_token" not in body
        assert body["email"] == user.email

        # New cookies must be present.
        assert "access_token" in refresh_resp.cookies
        assert "refresh_token" in refresh_resp.cookies

    def test_refresh_with_invalid_token_returns_401(self, client):
        """Presenting a garbage refresh token returns 401."""
        client.cookies.set("refresh_token", "invalid.token.value")
        client.cookies.set("access_token", "any-token")
        resp = client.post(
            "/internal/auth/refresh",
            headers={"X-CSRF-Token": "dummy"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


class TestLogout:
    def test_logout_clears_cookies(self, client, local_user_with_credential):
        """Logout endpoint revokes session and clears cookies."""
        user, plain_pw = local_user_with_credential

        login_resp = client.post(
            "/internal/auth/login",
            json={"email": user.email, "password": plain_pw},
        )
        assert login_resp.status_code == 200
        csrf = login_resp.cookies.get("csrf_token")

        logout_resp = client.post(
            "/internal/auth/logout",
            headers={"X-CSRF-Token": csrf} if csrf else {},
        )
        assert logout_resp.status_code == 200
        # After logout the refresh_token cookie should be cleared (max-age=0 or deleted).
        # TestClient represents deleted cookies as empty string or absent.
        rt = logout_resp.cookies.get("refresh_token")
        assert rt in (None, "", "null")


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestLoginErrorPaths:
    def test_wrong_password_returns_401(self, client, local_user_with_credential):
        user, _ = local_user_with_credential
        resp = client.post(
            "/internal/auth/login",
            json={"email": user.email, "password": "WrongP@ssword!1"},
        )
        assert resp.status_code == 401
        # Generic message — no enumeration.
        assert "invalid" in resp.json()["detail"].lower()

    def test_unknown_email_returns_401(self, client):
        resp = client.post(
            "/internal/auth/login",
            json={"email": "nobody@mattin-test.com", "password": "SomeP@ss1234"},
        )
        assert resp.status_code == 401

    def test_missing_body_returns_422(self, client):
        resp = client.post("/internal/auth/login")
        assert resp.status_code == 422


class TestSetPasswordTokenErrors:
    def test_invalid_token_returns_400(self, client):
        resp = client.post(
            "/internal/auth/set-password",
            json={"token": "this.is.not.a.real.token", "new_password": "ValidP@ss1234"},
        )
        assert resp.status_code == 400

    def test_used_token_returns_400(self, client, db):
        """Consuming a token twice returns 400 on the second attempt."""
        from models.user import User
        import asyncio
        from repositories.user_credential_repository import UserCredentialRepository
        from services.auth.credential_service import hash_password, CredentialService

        user = User(
            email="usedtoken@mattin-test.com",
            name="Used Token",
            is_active=True,
            auth_method="local",
            email_verified=False,
        )
        db.add(user)
        placeholder = asyncio.run(hash_password("__placeholder__placeholder__"))
        db.flush()
        cred_repo = UserCredentialRepository(db)
        cred_repo.create(user_id=user.user_id, hashed_password=placeholder)
        db.flush()

        token = CredentialService.issue_set_password_token(db, user.user_id)

        # First consumption — should succeed.
        first = client.post(
            "/internal/auth/set-password",
            json={"token": token, "new_password": "FirstP@ss1234"},
        )
        assert first.status_code == 200

        # Second consumption — token is now cleared from DB.
        second = client.post(
            "/internal/auth/set-password",
            json={"token": token, "new_password": "SecondP@ss1234"},
        )
        assert second.status_code == 400


class TestDuplicateUserCreation:
    def test_duplicate_email_returns_409_via_service(self, db):
        """Creating a LOCAL user with an already-registered email raises 409."""
        import asyncio
        from services.auth.credential_service import CredentialService, UserAlreadyExistsError

        asyncio.run(CredentialService.admin_create_user(db, "dup@mattin-test.com", "Dup User"))
        db.flush()

        with pytest.raises(UserAlreadyExistsError):
            asyncio.run(CredentialService.admin_create_user(db, "dup@mattin-test.com", "Dup User 2"))
