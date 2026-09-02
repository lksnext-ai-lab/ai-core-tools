"""
Integration tests for the middlewares endpoints.

Endpoints under test:
  - GET    /internal/apps/{app_id}/middlewares               (list middlewares)
  - GET    /internal/apps/{app_id}/middlewares/{middleware_id} (get middleware details, 0 = template)
  - POST   /internal/apps/{app_id}/middlewares/{middleware_id} (create or update middleware)
  - DELETE /internal/apps/{app_id}/middlewares/{middleware_id} (delete middleware)

This is the router-level coverage that was missing: unit tests exercise
GuardrailsMiddleware/monitoring directly and
tests/integration/tools/test_agent_middleware_chain_integration.py exercises
the LangChain wiring, but nothing previously went through the actual HTTP
CRUD surface — in particular, the cross-app mcp_config_ids IDOR fixed in
95acc540 had no regression test.
"""

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def middlewares_url(app_id: int, middleware_id) -> str:
    return f"/internal/apps/{app_id}/middlewares/{middleware_id}"


def middlewares_list_url(app_id: int) -> str:
    return f"/internal/apps/{app_id}/middlewares"


def middleware_payload(
    name: str = "Test Middleware",
    description: str = "A test middleware",
    middleware_type: str = "monitoring",
    config: dict = None,
    mcp_config_ids: list = None,
) -> dict:
    return {
        "name": name,
        "description": description,
        "middleware_type": middleware_type,
        "config": config,
        "mcp_config_ids": mcp_config_ids or [],
    }


@pytest.fixture
def other_app(db, fake_user):
    """A second App, distinct from fake_app, owned by the same fake_user."""
    from models.app import App

    app_obj = App(
        name="Other Workspace",
        slug="other-workspace-fixture",
        owner_id=fake_user.user_id,
        agent_rate_limit=0,
        max_file_size_mb=10,
    )
    db.add(app_obj)
    db.flush()
    return app_obj


@pytest.fixture
def other_app_mcp_config(db, other_app):
    """An MCPConfig that belongs to other_app, not fake_app."""
    from models.mcp_config import MCPConfig

    mcp = MCPConfig(
        name="Other App MCP",
        description="Belongs to a different app",
        config={"url": "https://example.com/mcp"},
        app_id=other_app.app_id,
    )
    db.add(mcp)
    db.flush()
    return mcp


@pytest.fixture
def outsider_headers(db):
    """Auth headers for a user with NO relationship to fake_app at all (not the
    owner, not a collaborator) — used to assert role enforcement actually
    rejects unaffiliated users, as opposed to auth_headers/fake_user, who
    is always the OWNER of fake_app via App.owner_id."""
    from models.user import User
    from utils.local_auth_tokens import mint_access_token

    user = User(email="outsider@mattin-test.com", name="Outsider", is_active=True, platform_role="editor")
    db.add(user)
    db.flush()

    token, _ = mint_access_token(user.user_id, user.email, user.name)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def fake_app_mcp_config(db, fake_app):
    """An MCPConfig that legitimately belongs to fake_app."""
    from models.mcp_config import MCPConfig

    mcp = MCPConfig(
        name="Fake App MCP",
        description="Belongs to fake_app",
        config={"url": "https://example.com/mcp"},
        app_id=fake_app.app_id,
    )
    db.add(mcp)
    db.flush()
    return mcp


# ---------------------------------------------------------------------------
# List middlewares
# ---------------------------------------------------------------------------

class TestListMiddlewares:
    def test_list_returns_empty_for_new_app(self, client, fake_app, owner_headers, db):
        db.flush()
        response = client.get(middlewares_list_url(fake_app.app_id), headers=owner_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_list_requires_authentication(self, client, fake_app, db):
        db.flush()
        response = client.get(middlewares_list_url(fake_app.app_id))
        assert response.status_code in (401, 403)

    def test_list_does_not_leak_other_apps_middlewares(
        self, client, fake_app, other_app, owner_headers, db
    ):
        """A middleware created in other_app must not show up when listing fake_app."""
        db.flush()
        create_resp = client.post(
            middlewares_url(other_app.app_id, 0),
            json=middleware_payload(name="Other App Middleware"),
            headers=owner_headers,
        )
        assert create_resp.status_code == 200

        list_resp = client.get(middlewares_list_url(fake_app.app_id), headers=owner_headers)
        assert list_resp.status_code == 200
        assert list_resp.json() == []


# ---------------------------------------------------------------------------
# Get middleware
# ---------------------------------------------------------------------------

class TestGetMiddleware:
    def test_get_template_for_id_zero(self, client, fake_app, owner_headers, db):
        db.flush()
        response = client.get(middlewares_url(fake_app.app_id, 0), headers=owner_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["middleware_id"] == 0
        assert data["name"] == ""

    def test_get_returns_404_for_missing_middleware(self, client, fake_app, owner_headers, db):
        db.flush()
        response = client.get(middlewares_url(fake_app.app_id, 99999), headers=owner_headers)
        assert response.status_code == 404

    def test_get_returns_404_for_other_apps_middleware(
        self, client, fake_app, other_app, owner_headers, db
    ):
        """A middleware belonging to other_app must 404 when fetched via fake_app's URL."""
        db.flush()
        create_resp = client.post(
            middlewares_url(other_app.app_id, 0),
            json=middleware_payload(name="Other App Middleware"),
            headers=owner_headers,
        )
        other_middleware_id = create_resp.json()["middleware_id"]

        response = client.get(middlewares_url(fake_app.app_id, other_middleware_id), headers=owner_headers)
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Create / update middleware
# ---------------------------------------------------------------------------

class TestCreateOrUpdateMiddleware:
    def test_create_returns_200_with_expected_fields(self, client, fake_app, owner_headers, db):
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(name="Guardrails", middleware_type="guardrails", config={"custom_prompt": "be nice"}),
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Guardrails"
        assert data["middleware_type"] == "guardrails"
        assert data["config"] == {"custom_prompt": "be nice"}
        assert data["middleware_id"] != 0

    def test_update_existing_middleware(self, client, fake_app, owner_headers, db):
        db.flush()
        create_resp = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(name="Original name"),
            headers=owner_headers,
        )
        middleware_id = create_resp.json()["middleware_id"]

        update_resp = client.post(
            middlewares_url(fake_app.app_id, middleware_id),
            json=middleware_payload(name="Renamed"),
            headers=owner_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Renamed"
        assert update_resp.json()["middleware_id"] == middleware_id

    def test_invalid_middleware_type_returns_422(self, client, fake_app, owner_headers, db):
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(middleware_type="not_a_real_type"),
            headers=owner_headers,
        )
        assert response.status_code == 422

    def test_create_requires_administrator_role(self, client, fake_app, outsider_headers, db):
        """A user with no app affiliation (plain authenticated user) must be rejected."""
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(),
            headers=outsider_headers,
        )
        assert response.status_code == 403

    def test_create_requires_authentication(self, client, fake_app, db):
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(),
        )
        assert response.status_code in (401, 403)

    def test_update_returns_404_for_other_apps_middleware(
        self, client, fake_app, other_app, owner_headers, db
    ):
        """Attempting to update other_app's middleware via fake_app's URL must 404,
        not silently update it."""
        db.flush()
        create_resp = client.post(
            middlewares_url(other_app.app_id, 0),
            json=middleware_payload(name="Other App Middleware"),
            headers=owner_headers,
        )
        other_middleware_id = create_resp.json()["middleware_id"]

        response = client.post(
            middlewares_url(fake_app.app_id, other_middleware_id),
            json=middleware_payload(name="Hijacked"),
            headers=owner_headers,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Cross-app MCP config IDOR regression (fixed in 95acc540)
# ---------------------------------------------------------------------------

class TestMcpConfigCrossAppIdor:
    def test_create_rejects_mcp_config_from_another_app(
        self, client, fake_app, other_app_mcp_config, owner_headers, db
    ):
        """Creating a middleware in fake_app while pointing mcp_config_ids at an
        MCPConfig that belongs to other_app must not link it — regression test
        for the cross-app IDOR fixed in 95acc540."""
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(mcp_config_ids=[other_app_mcp_config.config_id]),
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert response.json()["mcp_config_ids"] == []

    def test_create_keeps_mcp_config_from_same_app(
        self, client, fake_app, fake_app_mcp_config, owner_headers, db
    ):
        """Sanity check: a legitimate same-app MCPConfig IS linked, so the fix
        above is a filter, not a blanket drop."""
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(mcp_config_ids=[fake_app_mcp_config.config_id]),
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert response.json()["mcp_config_ids"] == [fake_app_mcp_config.config_id]

    def test_create_mixed_valid_and_cross_app_ids_keeps_only_valid(
        self, client, fake_app, fake_app_mcp_config, other_app_mcp_config, owner_headers, db
    ):
        db.flush()
        response = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(
                mcp_config_ids=[fake_app_mcp_config.config_id, other_app_mcp_config.config_id]
            ),
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert response.json()["mcp_config_ids"] == [fake_app_mcp_config.config_id]

    def test_update_cannot_relink_to_cross_app_mcp_config(
        self, client, fake_app, fake_app_mcp_config, other_app_mcp_config, owner_headers, db
    ):
        """A middleware first linked to a legitimate MCPConfig must not pick up
        a foreign one on a subsequent update."""
        db.flush()
        create_resp = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(mcp_config_ids=[fake_app_mcp_config.config_id]),
            headers=owner_headers,
        )
        middleware_id = create_resp.json()["middleware_id"]
        assert create_resp.json()["mcp_config_ids"] == [fake_app_mcp_config.config_id]

        update_resp = client.post(
            middlewares_url(fake_app.app_id, middleware_id),
            json=middleware_payload(mcp_config_ids=[other_app_mcp_config.config_id]),
            headers=owner_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["mcp_config_ids"] == []


# ---------------------------------------------------------------------------
# Delete middleware
# ---------------------------------------------------------------------------

class TestDeleteMiddleware:
    def test_delete_removes_middleware(self, client, fake_app, owner_headers, db):
        db.flush()
        create_resp = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(),
            headers=owner_headers,
        )
        middleware_id = create_resp.json()["middleware_id"]

        delete_resp = client.delete(middlewares_url(fake_app.app_id, middleware_id), headers=owner_headers)
        assert delete_resp.status_code == 200

        get_resp = client.get(middlewares_url(fake_app.app_id, middleware_id), headers=owner_headers)
        assert get_resp.status_code == 404

    def test_delete_returns_404_for_missing_middleware(self, client, fake_app, owner_headers, db):
        db.flush()
        response = client.delete(middlewares_url(fake_app.app_id, 99999), headers=owner_headers)
        assert response.status_code == 404

    def test_delete_returns_404_for_other_apps_middleware(
        self, client, fake_app, other_app, owner_headers, db
    ):
        db.flush()
        create_resp = client.post(
            middlewares_url(other_app.app_id, 0),
            json=middleware_payload(name="Other App Middleware"),
            headers=owner_headers,
        )
        other_middleware_id = create_resp.json()["middleware_id"]

        response = client.delete(middlewares_url(fake_app.app_id, other_middleware_id), headers=owner_headers)
        assert response.status_code == 404

    def test_delete_requires_administrator_role(self, client, fake_app, outsider_headers, owner_headers, db):
        db.flush()
        create_resp = client.post(
            middlewares_url(fake_app.app_id, 0),
            json=middleware_payload(),
            headers=owner_headers,
        )
        middleware_id = create_resp.json()["middleware_id"]

        response = client.delete(middlewares_url(fake_app.app_id, middleware_id), headers=outsider_headers)
        assert response.status_code == 403
