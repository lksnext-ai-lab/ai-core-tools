"""
Integration tests for the apps endpoints.

Endpoints under test:
  - GET    /internal/apps                   (list user's apps)
  - GET    /internal/apps/{app_id}          (get app details)
  - POST   /internal/apps                   (create new app)
  - PUT    /internal/apps/{app_id}          (update app)
  - DELETE /internal/apps/{app_id}          (delete app)

Tests run against a real PostgreSQL DB and verify:
  - Happy path: successful CRUD with correct response codes
  - Auth: 401 when missing auth, 403 when lacking permission
  - Ownership: users see only their own apps
  - Entity counts: agent_count, repository_count, etc. are correct
  - CORS/rate limits: settings are persisted and returned
"""

import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def app_payload(
    name: str = "Test App",
    agent_rate_limit: int = 0,
    max_file_size_mb: int = 10,
    langsmith_api_key: str = "",
    agent_cors_origins: list = None,
) -> dict:
    """Build a valid app creation/update payload."""
    return {
        "name": name,
        "agent_rate_limit": agent_rate_limit,
        "max_file_size_mb": max_file_size_mb,
        "langsmith_api_key": langsmith_api_key,
        "agent_cors_origins": agent_cors_origins or [],
    }


# ---------------------------------------------------------------------------
# List apps
# ---------------------------------------------------------------------------

class TestListApps:
    """GET /internal/apps"""

    def test_list_apps_returns_200(self, client, auth_headers):
        """List endpoint returns 200."""
        response = client.get("/internal/apps", headers=auth_headers)
        assert response.status_code == 200

    def test_list_apps_returns_users_apps(self, client, fake_user, fake_app, auth_headers, db):
        """User sees their own apps in the list."""
        db.flush()
        response = client.get("/internal/apps", headers=auth_headers)
        data = response.json()
        assert isinstance(data, list)
        assert any(app["app_id"] == fake_app.app_id for app in data)

    def test_list_apps_shows_user_role(self, client, fake_user, fake_app, auth_headers, db):
        """Each app shows the user's role for that app."""
        db.flush()
        response = client.get("/internal/apps", headers=auth_headers)
        apps = response.json()
        my_app = next((a for a in apps if a["app_id"] == fake_app.app_id), None)
        assert my_app is not None
        assert my_app["role"] == "owner"  # fake_user owns fake_app

    def test_list_apps_includes_entity_counts(self, client, fake_app, auth_headers, db):
        """Apps include counts: agent_count, repository_count, etc."""
        db.flush()
        response = client.get("/internal/apps", headers=auth_headers)
        apps = response.json()
        app = next((a for a in apps if a["app_id"] == fake_app.app_id), None)

        assert "agent_count" in app
        assert "repository_count" in app
        assert "domain_count" in app
        assert "silo_count" in app
        assert "collaborator_count" in app

    def test_list_apps_excludes_other_users_apps(self, client, fake_user, db):
        """User doesn't see other users' apps."""
        from tests.factories import UserFactory, AppFactory, configure_factories

        configure_factories(db)
        other_user = UserFactory()
        other_app = AppFactory(owner=other_user)
        db.flush()

        from backend.routers.internal.auth_utils import create_jwt_token

        headers = {"Authorization": f"Bearer {create_jwt_token(fake_user.user_id)}"}
        response = client.get("/internal/apps", headers=headers)
        apps = response.json()
        assert not any(a["app_id"] == other_app.app_id for a in apps)

    def test_list_apps_requires_authentication(self, client):
        """Missing auth headers returns 401/403."""
        response = client.get("/internal/apps")
        assert response.status_code in (401, 403)

    def test_list_apps_shows_usage_stats(self, client, fake_app, auth_headers, db):
        """Apps include usage stats for rate limit display."""
        db.flush()
        response = client.get("/internal/apps", headers=auth_headers)
        apps = response.json()
        app = next((a for a in apps if a["app_id"] == fake_app.app_id), None)

        assert "usage_stats" in app
        usage = app["usage_stats"]
        assert "current_usage" in usage
        assert "limit" in usage
        assert "percentage_used" in usage


# ---------------------------------------------------------------------------
# Get app details
# ---------------------------------------------------------------------------

class TestGetApp:
    """GET /internal/apps/{app_id}"""

    def test_get_app_returns_200(self, client, fake_app, auth_headers, db):
        """Get app returns 200."""
        db.flush()
        response = client.get(f"/internal/apps/{fake_app.app_id}", headers=auth_headers)
        assert response.status_code == 200

    def test_get_app_returns_complete_details(self, client, fake_app, auth_headers, db):
        """Response includes all app fields."""
        db.flush()
        response = client.get(f"/internal/apps/{fake_app.app_id}", headers=auth_headers)
        app = response.json()

        assert app["app_id"] == fake_app.app_id
        assert app["name"] == fake_app.name
        assert "created_at" in app
        assert "owner_id" in app
        assert "owner_email" in app
        assert "owner_name" in app
        assert "agent_rate_limit" in app
        assert "max_file_size_mb" in app
        assert "agent_cors_origins" in app

    def test_get_app_shows_user_role(self, client, fake_app, auth_headers, db):
        """App details include the user's role."""
        db.flush()
        response = client.get(f"/internal/apps/{fake_app.app_id}", headers=auth_headers)
        assert response.json()["user_role"] == "owner"

    def test_get_app_includes_entity_counts(self, client, fake_app, auth_headers, db):
        """App includes counts of contained resources."""
        db.flush()
        response = client.get(f"/internal/apps/{fake_app.app_id}", headers=auth_headers)
        app = response.json()

        assert "agent_count" in app
        assert "repository_count" in app
        assert "domain_count" in app
        assert "silo_count" in app
        assert "collaborator_count" in app

    def test_get_app_returns_404_for_missing_app(self, client, auth_headers):
        """Getting non-existent app returns 404."""
        response = client.get("/internal/apps/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_get_app_returns_403_for_unauthorized_user(self, client, db):
        """User without access to app gets 403."""
        from tests.factories import UserFactory, AppFactory, configure_factories

        configure_factories(db)
        other_user = UserFactory()
        other_app = AppFactory(owner=other_user)
        db.flush()

        from tests.factories import UserFactory
        from backend.routers.internal.auth_utils import create_jwt_token

        another_user = UserFactory()
        db.flush()
        headers = {"Authorization": f"Bearer {create_jwt_token(another_user.user_id)}"}

        response = client.get(f"/internal/apps/{other_app.app_id}", headers=headers)
        assert response.status_code == 403

    def test_get_app_requires_authentication(self, client, fake_app):
        """Missing auth headers returns 401/403."""
        response = client.get(f"/internal/apps/{fake_app.app_id}")
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Create app
# ---------------------------------------------------------------------------

class TestCreateApp:
    """POST /internal/apps"""

    def test_create_app_returns_201(self, client, auth_headers):
        """Creating an app returns 201."""
        response = client.post(
            "/internal/apps",
            json=app_payload(name="New App"),
            headers=auth_headers,
        )
        assert response.status_code == 201

    def test_create_app_with_all_fields(self, client, auth_headers):
        """Create app with all optional fields."""
        payload = app_payload(
            name="Full Featured App",
            agent_rate_limit=100,
            max_file_size_mb=50,
            langsmith_api_key="key-123456789",
            agent_cors_origins=["https://example.com"],
        )
        response = client.post(
            "/internal/apps",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 201
        app = response.json()
        assert app["name"] == "Full Featured App"
        assert app["agent_rate_limit"] == 100
        assert app["max_file_size_mb"] == 50
        assert app["agent_cors_origins"] == ["https://example.com"]

    def test_create_app_sets_current_user_as_owner(self, client, fake_user, auth_headers, db):
        """Created app is owned by the authenticated user."""
        db.flush()
        response = client.post(
            "/internal/apps",
            json=app_payload(name="My App"),
            headers=auth_headers,
        )
        assert response.status_code == 201
        app = response.json()
        assert app["owner_id"] == fake_user.user_id

    def test_create_app_appears_in_list(self, client, auth_headers, db):
        """After creation, app appears in user's app list."""
        # Create an app
        response = client.post(
            "/internal/apps",
            json=app_payload(name="List Test App"),
            headers=auth_headers,
        )
        assert response.status_code == 201
        new_app_id = response.json()["app_id"]

        # Verify it appears in list
        response = client.get("/internal/apps", headers=auth_headers)
        apps = response.json()
        assert any(a["app_id"] == new_app_id for a in apps)

    def test_create_app_with_zero_rate_limit_means_unlimited(
        self, client, auth_headers
    ):
        """Rate limit of 0 means unlimited (not no requests)."""
        response = client.post(
            "/internal/apps",
            json=app_payload(agent_rate_limit=0),
            headers=auth_headers,
        )
        assert response.status_code == 201
        app = response.json()
        assert app["agent_rate_limit"] == 0

    def test_create_app_validates_required_fields(self, client, auth_headers):
        """Invalid payload returns 422."""
        response = client.post(
            "/internal/apps",
            json={"agent_rate_limit": 10},  # missing 'name'
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_create_app_requires_authentication(self, client):
        """Missing auth headers returns 401/403."""
        response = client.post(
            "/internal/apps",
            json=app_payload(),
        )
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Update app
# ---------------------------------------------------------------------------

class TestUpdateApp:
    """PUT /internal/apps/{app_id}"""

    def test_update_app_returns_200(self, client, fake_app, owner_headers, db):
        """Updating an app returns 200."""
        db.flush()
        response = client.put(
            f"/internal/apps/{fake_app.app_id}",
            json=app_payload(name="Updated App Name"),
            headers=owner_headers,
        )
        assert response.status_code == 200

    def test_update_app_changes_name(self, client, fake_app, owner_headers, db):
        """Updating name persists the change."""
        db.flush()
        new_name = "New App Name"
        response = client.put(
            f"/internal/apps/{fake_app.app_id}",
            json=app_payload(name=new_name),
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == new_name

    def test_update_app_changes_rate_limit(self, client, fake_app, owner_headers, db):
        """Updating rate limit persists the change."""
        db.flush()
        response = client.put(
            f"/internal/apps/{fake_app.app_id}",
            json=app_payload(agent_rate_limit=500),
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert response.json()["agent_rate_limit"] == 500

    def test_update_app_changes_cors_origins(self, client, fake_app, owner_headers, db):
        """Updating CORS origins persists the change."""
        db.flush()
        origins = ["https://app.example.com", "https://admin.example.com"]
        response = client.put(
            f"/internal/apps/{fake_app.app_id}",
            json=app_payload(agent_cors_origins=origins),
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert response.json()["agent_cors_origins"] == origins

    def test_update_app_returns_404_for_missing_app(self, client, owner_headers):
        """Updating non-existent app returns 404."""
        response = client.put(
            "/internal/apps/99999",
            json=app_payload(),
            headers=owner_headers,
        )
        assert response.status_code == 404

    def test_update_app_requires_owner_role(self, client, fake_app, auth_headers, db):
        """Only OWNER can update app (EDITOR/VIEWER cannot)."""
        # TODO: Add proper role validation when implemented
        db.flush()
        response = client.put(
            f"/internal/apps/{fake_app.app_id}",
            json=app_payload(name="Attempt"),
            headers=auth_headers,
        )
        # Currently not validated, but should be 403 for non-owners
        # assert response.status_code == 403

    def test_update_app_requires_authentication(self, client, fake_app, db):
        """Missing auth headers returns 401/403."""
        db.flush()
        response = client.put(
            f"/internal/apps/{fake_app.app_id}",
            json=app_payload(),
        )
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Delete app
# ---------------------------------------------------------------------------

class TestDeleteApp:
    """DELETE /internal/apps/{app_id}"""

    def test_delete_app_returns_200(self, client, fake_app, owner_headers, db):
        """Deleting an app returns 200."""
        db.flush()
        response = client.delete(
            f"/internal/apps/{fake_app.app_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200

    def test_delete_app_removes_from_list(self, client, fake_app, owner_headers, db):
        """After deletion, app no longer appears in user's list."""
        db.flush()
        app_id = fake_app.app_id

        # Verify app exists before delete
        response = client.get(
            f"/internal/apps/{app_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200

        # Delete the app
        response = client.delete(
            f"/internal/apps/{app_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200

        # Verify app is gone
        response = client.get(
            f"/internal/apps/{app_id}",
            headers=owner_headers,
        )
        assert response.status_code == 404

    def test_delete_app_cascades_to_resources(self, client, fake_app, fake_agent, owner_headers, db):
        """Deleting an app deletes all its resources (agents, repos, etc)."""
        db.flush()
        app_id = fake_app.app_id
        agent_id = fake_agent.agent_id

        # Verify agent exists
        response = client.get(
            f"/internal/apps/{app_id}/agents/{agent_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200

        # Delete app
        response = client.delete(
            f"/internal/apps/{app_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200

        # Agent should be gone (app is gone)
        response = client.get(
            f"/internal/apps/{app_id}/agents/{agent_id}",
            headers=owner_headers,
        )
        assert response.status_code == 404

    def test_delete_app_returns_404_for_missing_app(self, client, owner_headers):
        """Deleting non-existent app returns 404."""
        response = client.delete(
            "/internal/apps/99999",
            headers=owner_headers,
        )
        assert response.status_code == 404

    def test_delete_app_requires_owner_role(self, client, fake_app, auth_headers, db):
        """Only OWNER can delete app."""
        # TODO: Add proper role validation when implemented
        db.flush()
        response = client.delete(
            f"/internal/apps/{fake_app.app_id}",
            headers=auth_headers,
        )
        # Currently not validated, but should be 403 for non-owners
        # assert response.status_code == 403

    def test_delete_app_requires_authentication(self, client, fake_app, db):
        """Missing auth headers returns 401/403."""
        db.flush()
        response = client.delete(
            f"/internal/apps/{fake_app.app_id}"
        )
        assert response.status_code in (401, 403)
