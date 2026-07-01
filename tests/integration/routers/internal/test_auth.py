"""
Integration tests for the auth router.

POST /internal/auth/dev-login was removed in step_008 (FAKE mode retired).
The tests below serve as regression guards to confirm:
  1. The endpoint is gone (404).
  2. Protected endpoints still enforce authentication correctly.
  3. A valid LOCAL-issuer Bearer token grants access to protected endpoints.

Auth mode: AICT_LOGIN=LOCAL (set via pytest-env in pyproject.toml).
"""

import pytest


# ---------------------------------------------------------------------------
# Regression guard: dev-login endpoint is gone
# ---------------------------------------------------------------------------


class TestDevLoginRemoved:
    """POST /internal/auth/dev-login must return 404 in all currently supported modes."""

    def test_dev_login_returns_404(self, client):
        """Confirms the dev-login shortcut was retired — endpoint must not exist."""
        response = client.post(
            "/internal/auth/dev-login",
            json={"email": "anyuser@mattin-test.com"},
        )
        assert response.status_code == 404

    def test_dev_login_with_empty_body_returns_404(self, client):
        """Even malformed requests to the retired endpoint get 404, not 422."""
        response = client.post("/internal/auth/dev-login", json={})
        assert response.status_code == 404

    def test_dev_login_get_method_also_returns_404(self, client):
        """Method mismatch on a non-existent route → 404 or 405 (not 200)."""
        response = client.get("/internal/auth/dev-login")
        assert response.status_code in (404, 405)


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

    def test_valid_local_token_allows_access_to_apps_list(
        self, client, auth_headers, fake_user, db
    ):
        """Authenticated user with a LOCAL-issuer token can list their apps."""
        response = client.get("/internal/apps", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_valid_token_allows_pending_invitations(
        self, client, auth_headers, fake_user, db
    ):
        """LOCAL token works on any authenticated endpoint (pending invitations)."""
        response = client.get(
            "/internal/auth/pending-invitations",
            headers=auth_headers,
        )
        assert response.status_code in (200, 204)
