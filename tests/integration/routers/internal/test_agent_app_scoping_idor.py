"""
Regression tests for the agent cross-tenant IDOR fix.

Endpoints under test:
  - GET  /internal/apps/{app_id}/agents/{agent_id}   (get agent details)
  - POST /internal/apps/{app_id}/agents/{agent_id}   (create or update agent)

Bug: both endpoints only checked the caller's role on ``app_id`` from the URL path,
but never verified that ``agent_id`` actually belongs to that app. An EDITOR/OWNER of
App A could therefore:
  - read any other tenant's agent (system prompt, config) via GET /apps/A/agents/{b_id}
  - overwrite/move App B's agent into App A (and its AI service/silo) via
    POST /apps/A/agents/{b_id}

These tests use two separate Apps (``fake_app`` = App A, ``other_app`` = App B, both
owned by the same ``fake_user`` so the app-level RBAC on App A passes) to prove the
agent-ownership check is now enforced independently of the app-level role check.
"""

import pytest

from tests.factories import AppFactory, AgentFactory, AIServiceFactory, configure_factories


@pytest.fixture
def other_app(db, fake_user):
    """A second App (App B) owned by the SAME user as fake_app (App A).

    Same owner so that the app-level RBAC dependency (which only checks the role on
    the path's app_id) can never be the reason a cross-app request is rejected --
    isolating the assertions to the agent-ownership check under test.
    """
    configure_factories(db)
    return AppFactory(owner_id=fake_user.user_id)


@pytest.fixture
def other_agent(db, other_app):
    """An Agent belonging to App B, with its own AI service."""
    configure_factories(db)
    ai_service = AIServiceFactory(app=other_app)
    agent = AgentFactory(
        app=other_app,
        ai_service=ai_service,
        name="Other App's Secret Agent",
        system_prompt="TOP SECRET system prompt belonging to App B",
    )
    db.flush()
    return agent


def _editor_headers(fake_user, owner_headers):
    """owner_headers already makes fake_user OWNER of fake_app (app-level RBAC);
    bump the platform-wide role too so the global require_editor_for_writes gate
    (unrelated to app-level RBAC) lets POST/DELETE through.
    """
    fake_user.platform_role = "editor"
    return owner_headers


class TestGetAgentCrossAppScoping:
    """GET /internal/apps/{app_id}/agents/{agent_id} must 404 across tenants."""

    def test_get_other_apps_agent_returns_404(
        self, client, fake_app, other_agent, owner_headers, db
    ):
        """OWNER of App A requesting App B's agent via App A's path gets 404, not the agent."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{other_agent.agent_id}",
            headers=owner_headers,
        )
        assert response.status_code == 404

    def test_get_own_app_agent_still_works(
        self, client, fake_app, fake_agent, owner_headers, db
    ):
        """Sanity check: same-app GET is unaffected by the fix."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert response.json()["agent_id"] == fake_agent.agent_id

    def test_get_new_agent_sentinel_still_works(
        self, client, fake_app, owner_headers, db
    ):
        """agent_id=0 (new-agent form data) is exempt from the ownership check."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert response.json()["agent_id"] == 0


class TestUpdateAgentCrossAppScoping:
    """POST /internal/apps/{app_id}/agents/{agent_id} must 404, not hijack, across tenants."""

    def test_update_other_apps_agent_returns_404_and_leaves_it_unchanged(
        self, client, fake_app, other_agent, fake_user, owner_headers, db
    ):
        """OWNER of App A posting to App B's agent via App A's path gets 404, and App B's
        agent row (app_id, name, system_prompt) is left completely unchanged."""
        headers = _editor_headers(fake_user, owner_headers)
        db.flush()

        original_app_id = other_agent.app_id
        original_name = other_agent.name
        original_system_prompt = other_agent.system_prompt
        other_agent_id = other_agent.agent_id

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{other_agent_id}",
            json={
                "name": "Hijacked Agent",
                "description": "",
                "system_prompt": "Overwritten by attacker",
                "prompt_template": "",
                "type": "agent",
                "is_tool": False,
                "has_memory": False,
                "service_id": None,
                "silo_id": None,
                "output_parser_id": None,
                "temperature": 0.7,
                "tool_ids": [],
                "mcp_config_ids": [],
                "skill_ids": [],
            },
            headers=headers,
        )
        assert response.status_code == 404

        # Re-fetch App B's agent row from the DB to prove it was never touched.
        from models.agent import Agent as AgentModel

        db.expire_all()
        persisted = db.query(AgentModel).filter(AgentModel.agent_id == other_agent_id).one()
        assert persisted.app_id == original_app_id
        assert persisted.name == original_name
        assert persisted.system_prompt == original_system_prompt

    def test_update_own_app_agent_still_works(
        self, client, fake_app, fake_agent, fake_user, owner_headers, db
    ):
        """Sanity check: same-app update is unaffected by the fix."""
        headers = _editor_headers(fake_user, owner_headers)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json={
                "name": "Updated Name",
                "description": "",
                "system_prompt": "Updated prompt",
                "prompt_template": "",
                "type": "agent",
                "is_tool": False,
                "has_memory": False,
                "service_id": None,
                "silo_id": None,
                "output_parser_id": None,
                "temperature": 0.7,
                "tool_ids": [],
                "mcp_config_ids": [],
                "skill_ids": [],
            },
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    def test_create_new_agent_still_works(
        self, client, fake_app, fake_ai_service, fake_user, owner_headers, db
    ):
        """Sanity check: create (agent_id=0) is unaffected by the fix."""
        headers = _editor_headers(fake_user, owner_headers)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json={
                "name": "Brand New Agent",
                "description": "",
                "system_prompt": "New prompt",
                "prompt_template": "",
                "type": "agent",
                "is_tool": False,
                "has_memory": False,
                "service_id": fake_ai_service.service_id,
                "silo_id": None,
                "output_parser_id": None,
                "temperature": 0.7,
                "tool_ids": [],
                "mcp_config_ids": [],
                "skill_ids": [],
            },
            headers=headers,
        )
        assert response.status_code in (200, 201)
        body = response.json()
        assert body["name"] == "Brand New Agent"
        assert body["agent_id"] != 0
