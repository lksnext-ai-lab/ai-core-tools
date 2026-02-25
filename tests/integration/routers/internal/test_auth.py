"""
Integration tests for the auth endpoints.
Tests run against a real test PostgreSQL DB (via conftest fixtures).

Endpoint under test: POST /internal/auth/dev-login
Auth mode required: AICT_LOGIN=FAKE (set via pytest-env in pyproject.toml)
"""

import pytest


# ---------------------------------------------------------------------------
# Dev login — happy path
# ---------------------------------------------------------------------------


class TestDevLogin:
    def test_successful_login_returns_token(self, client, fake_user, db):
        """Active user in FAKE mode gets a valid JWT."""
        db.flush()
        response = client.post(
            "/internal/auth/dev-login",
            json={"email": fake_user.email},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["access_token"]  # non-empty

    def test_successful_login_response_structure(self, client, fake_user, db):
        db.flush()
        response = client.post(
            "/internal/auth/dev-login",
            json={"email": fake_user.email},
        )
        data = response.json()
        assert "expires_at" in data
        assert "token_type" in data
        assert "user" in data

    def test_user_info_in_response(self, client, fake_user, db):
        db.flush()
        response = client.post(
            "/internal/auth/dev-login",
            json={"email": fake_user.email},
        )
        user_data = response.json()["user"]
        assert user_data["email"] == fake_user.email
        assert user_data["user_id"] == fake_user.user_id

    def test_email_lookup_is_case_insensitive(self, client, fake_user, db):
        """The endpoint lowercases the email before lookup."""
        db.flush()
        response = client.post(
            "/internal/auth/dev-login",
            json={"email": fake_user.email.upper()},
        )
        assert response.status_code == 200

    def test_token_can_authenticate_subsequent_request(self, client, fake_user, db):
        """Token from dev-login works as Bearer auth on a protected endpoint."""
        db.flush()
        login_resp = client.post(
            "/internal/auth/dev-login",
            json={"email": fake_user.email},
        )
        token = login_resp.json()["access_token"]

        # Any authenticated endpoint — use /internal/auth/pending-invitations
        # which just requires a valid user
        check_resp = client.get(
            "/internal/auth/pending-invitations",
            headers={"Authorization": f"Bearer {token}"},
        )
        # 200 or empty list — either way it authenticated
        assert check_resp.status_code in (200, 204)


# ---------------------------------------------------------------------------
# Dev login — error paths
# ---------------------------------------------------------------------------


class TestDevLoginErrors:
    def test_unknown_email_returns_401(self, client, db):
        response = client.post(
            "/internal/auth/dev-login",
            json={"email": "nobody@mattin-test.com"},
        )
        assert response.status_code == 401

    def test_inactive_user_returns_403(self, client, db):
        from models.user import User

        inactive = User(
            email="inactive@mattin-test.com",
            name="Inactive User",
            is_active=False,
        )
        db.add(inactive)
        db.flush()

        response = client.post(
            "/internal/auth/dev-login",
            json={"email": inactive.email},
        )
        assert response.status_code == 403

    def test_missing_email_field_returns_422(self, client):
        response = client.post("/internal/auth/dev-login", json={})
        assert response.status_code == 422

    def test_empty_body_returns_422(self, client):
        response = client.post("/internal/auth/dev-login")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Protected endpoint access
# ---------------------------------------------------------------------------


class TestProtectedEndpointAccess:
    def test_no_token_returns_401_or_403(self, client):
        """Accessing a protected endpoint without a token is denied."""
        response = client.get("/internal/apps")
        assert response.status_code in (401, 403)

    def test_invalid_token_returns_401_or_403(self, client):
        response = client.get(
            "/internal/apps",
            headers={"Authorization": "Bearer this-is-not-a-real-token"},
        )
        assert response.status_code in (401, 403)

    def test_valid_token_allows_access_to_apps_list(
        self, client, auth_headers, fake_user, db
    ):
        """Authenticated user can list their apps (even if the list is empty)."""
        response = client.get("/internal/apps", headers=auth_headers)
        assert response.status_code == 200
        # Empty list is fine — fake_user has no apps yet (only fake_app not linked here)
        assert isinstance(response.json(), list)
