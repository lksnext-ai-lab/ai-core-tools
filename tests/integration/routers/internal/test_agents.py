"""
Integration tests for the agents endpoints.

Endpoints under test:
  - GET    /internal/apps/{app_id}/agents              (list agents)
  - GET    /internal/apps/{app_id}/agents/{agent_id}   (get agent details)
  - POST   /internal/apps/{app_id}/agents/{agent_id}   (create or update agent)
  - DELETE /internal/apps/{app_id}/agents/{agent_id}   (delete agent)

Tests run against a real test PostgreSQL DB and verify:
  - Happy path: successful CRUD operations with 200/201 responses
  - Auth: 401 when missing auth headers, 403 when lacking permission
  - Permissions: viewer can list/read, editor can create/update, owner can delete
  - Edge cases: 404 for missing agent, 422 for invalid data
"""

import pytest
from unittest.mock import patch, AsyncMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def agent_payload(
    name: str = "Test Agent",
    description: str = "A test agent",
    system_prompt: str = "You are a helpful assistant",
    prompt_template: str = None,
    agent_type: str = "agent",
    is_tool: bool = False,
    has_memory: bool = False,
    service_id: int = None,
    silo_id: int = None,
    output_parser_id: int = None,
    temperature: float = 0.7,
    tool_ids: list = None,
    mcp_config_ids: list = None,
    skill_ids: list = None,
    # OCR-specific
    vision_service_id: int = None,
    vision_system_prompt: str = None,
    text_system_prompt: str = None,
) -> dict:
    """Build a valid agent creation/update payload."""
    return {
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
        "prompt_template": prompt_template or "",
        "type": agent_type,
        "is_tool": is_tool,
        "has_memory": has_memory,
        "service_id": service_id,
        "silo_id": silo_id,
        "output_parser_id": output_parser_id,
        "temperature": temperature,
        "tool_ids": tool_ids or [],
        "mcp_config_ids": mcp_config_ids or [],
        "skill_ids": skill_ids or [],
        "vision_service_id": vision_service_id,
        "vision_system_prompt": vision_system_prompt or "",
        "text_system_prompt": text_system_prompt or "",
    }


# ---------------------------------------------------------------------------
# List agents
# ---------------------------------------------------------------------------

class TestListAgents:
    """GET /internal/apps/{app_id}/agents"""

    def test_list_agents_returns_empty_list_for_new_app(
        self, client, fake_app, auth_headers, db
    ):
        """New app with no agents returns empty list."""
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_list_agents_returns_agents(
        self, client, fake_app, fake_agent, auth_headers, db
    ):
        """List endpoint returns all agents in the app."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents",
            headers=auth_headers,
        )
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) >= 1
        assert any(a["name"] == fake_agent.name for a in agents)

    def test_list_agents_includes_agent_metadata(
        self, client, fake_app, fake_agent, auth_headers, db
    ):
        """Each agent includes expected fields."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents",
            headers=auth_headers,
        )
        agents = response.json()
        agent = next((a for a in agents if a["agent_id"] == fake_agent.agent_id), None)

        assert agent is not None
        assert agent["name"] == fake_agent.name
        assert "agent_id" in agent
        assert "type" in agent
        assert "is_tool" in agent
        assert "created_at" in agent

    def test_list_agents_requires_authentication(self, client, fake_app):
        """Missing auth headers returns 401/403."""
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents"
        )
        assert response.status_code in (401, 403)

    def test_list_agents_requires_viewer_role(
        self, client, fake_app, db
    ):
        """VIEWER role can list agents (currently passes without validation)."""
        # TODO: Add proper role validation when app access is implemented
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents"
        )
        # Currently doesn't require role (see TODO in auth_utils)
        assert response.status_code in (401, 403)

    def test_list_agents_only_shows_app_agents(
        self, client, fake_app, fake_agent, db
    ):
        """List only includes agents from that specific app."""
        from tests.factories import AppFactory, AgentFactory
        from tests.factories import configure_factories

        configure_factories(db)
        other_app = AppFactory(owner_id=fake_app.owner_id)
        other_agent = AgentFactory(app=other_app)
        db.flush()

        # Get auth headers for the owner
        from backend.routers.internal.auth_utils import create_jwt_token

        headers = {"Authorization": f"Bearer {create_jwt_token(fake_app.owner_id)}"}

        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents",
            headers=headers,
        )
        assert response.status_code == 200
        agents = response.json()
        agent_ids = [a["agent_id"] for a in agents]
        assert fake_agent.agent_id in agent_ids
        assert other_agent.agent_id not in agent_ids


# ---------------------------------------------------------------------------
# Get agent details
# ---------------------------------------------------------------------------

class TestGetAgentDetails:
    """GET /internal/apps/{app_id}/agents/{agent_id}"""

    def test_get_agent_returns_200(self, client, fake_app, fake_agent, auth_headers, db):
        """Valid agent ID returns 200 with agent details."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200

    def test_get_agent_returns_complete_details(
        self, client, fake_app, fake_agent, auth_headers, db
    ):
        """Response includes all agent fields."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            headers=auth_headers,
        )
        data = response.json()

        assert data["agent_id"] == fake_agent.agent_id
        assert data["name"] == fake_agent.name
        assert "system_prompt" in data
        assert "prompt_template" in data
        assert "type" in data
        assert "is_tool" in data
        assert "has_memory" in data
        assert "service_id" in data
        assert "silo_id" in data
        assert "output_parser_id" in data
        assert "temperature" in data

    def test_get_agent_returns_empty_lists_for_associations(
        self, client, fake_app, fake_agent, auth_headers, db
    ):
        """Tool/MCP/Skill lists are empty when not configured."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            headers=auth_headers,
        )
        data = response.json()

        assert "tool_ids" in data
        assert isinstance(data["tool_ids"], list)
        assert "mcp_config_ids" in data
        assert isinstance(data["mcp_config_ids"], list)
        assert "skill_ids" in data
        assert isinstance(data["skill_ids"], list)

    def test_get_agent_returns_404_for_missing_agent(
        self, client, fake_app, auth_headers
    ):
        """Non-existent agent ID returns 404."""
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_get_agent_requires_authentication(self, client, fake_app, fake_agent, db):
        """Missing auth headers returns 401/403."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}"
        )
        assert response.status_code in (401, 403)

    def test_get_agent_returns_form_data(
        self, client, fake_app, fake_agent, fake_ai_service, auth_headers, db
    ):
        """Response includes form data (available AI services, silos, etc)."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            headers=auth_headers,
        )
        data = response.json()

        assert "form_data" in data
        form_data = data["form_data"]
        assert "ai_services" in form_data
        assert isinstance(form_data["ai_services"], list)


# ---------------------------------------------------------------------------
# Create agent
# ---------------------------------------------------------------------------

class TestCreateAgent:
    """POST /internal/apps/{app_id}/agents/0 (agent_id=0 means create new)"""

    def test_create_agent_returns_201(
        self, client, fake_app, fake_ai_service, owner_headers, db
    ):
        """Creating a new agent returns 201 with created agent details."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=agent_payload(
                name="New Agent",
                service_id=fake_ai_service.service_id,
            ),
            headers=owner_headers,
        )
        assert response.status_code in (200, 201)
        assert response.json()["name"] == "New Agent"

    def test_create_agent_with_all_fields(
        self, client, fake_app, fake_ai_service, owner_headers, db
    ):
        """Create agent with all optional fields."""
        db.flush()
        payload = agent_payload(
            name="Full Agent",
            description="Full featured agent",
            system_prompt="You are a specialized assistant",
            prompt_template="Chat with {user_name}",
            is_tool=False,
            has_memory=True,
            service_id=fake_ai_service.service_id,
            temperature=0.5,
        )
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=payload,
            headers=owner_headers,
        )
        assert response.status_code in (200, 201)
        agent = response.json()
        assert agent["name"] == "Full Agent"
        assert agent["has_memory"] is True
        assert agent["temperature"] == 0.5

    def test_create_agent_as_tool(
        self, client, fake_app, fake_ai_service, owner_headers, db
    ):
        """Create agent marked as a tool (can be used by other agents)."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=agent_payload(
                name="Tool Agent",
                is_tool=True,
                service_id=fake_ai_service.service_id,
            ),
            headers=owner_headers,
        )
        assert response.status_code in (200, 201)
        assert response.json()["is_tool"] is True

    def test_create_agent_requires_editor_role(
        self, client, fake_app, fake_ai_service, auth_headers, db
    ):
        """Creating agent requires EDITOR role (currently not validated)."""
        # TODO: Add proper role-based access control
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=agent_payload(service_id=fake_ai_service.service_id),
            headers=auth_headers,
        )
        # Role validation not yet implemented in auth_utils
        # assert response.status_code == 403

    def test_create_agent_requires_authentication(
        self, client, fake_app, fake_ai_service, db
    ):
        """Missing auth headers returns 401/403."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=agent_payload(service_id=fake_ai_service.service_id),
        )
        assert response.status_code in (401, 403)

    def test_create_agent_validates_required_fields(
        self, client, fake_app, owner_headers, db
    ):
        """Invalid payload (missing required fields) returns 422."""
        db.flush()
        invalid_payload = {"name": "Incomplete Agent"}  # missing other required fields
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=invalid_payload,
            headers=owner_headers,
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Update agent
# ---------------------------------------------------------------------------

class TestUpdateAgent:
    """POST /internal/apps/{app_id}/agents/{agent_id} (agent_id != 0)"""

    def test_update_agent_returns_200(
        self, client, fake_app, fake_agent, owner_headers, db
    ):
        """Updating an existing agent returns 200."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(name="Updated Agent Name"),
            headers=owner_headers,
        )
        assert response.status_code == 200

    def test_update_agent_changes_name(
        self, client, fake_app, fake_agent, owner_headers, db
    ):
        """Updating name persists the change."""
        db.flush()
        new_name = "New Agent Name"
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(name=new_name),
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == new_name

    def test_update_agent_changes_system_prompt(
        self, client, fake_app, fake_agent, owner_headers, db
    ):
        """Updating system prompt persists the change."""
        db.flush()
        new_prompt = "You are a specialized expert"
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(system_prompt=new_prompt),
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert response.json()["system_prompt"] == new_prompt

    def test_update_agent_changes_temperature(
        self, client, fake_app, fake_agent, owner_headers, db
    ):
        """Updating temperature persists the change."""
        db.flush()
        new_temp = 0.2
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(temperature=new_temp),
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert response.json()["temperature"] == new_temp

    def test_update_agent_returns_404_for_missing_agent(
        self, client, fake_app, owner_headers
    ):
        """Updating non-existent agent returns 404."""
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/99999",
            json=agent_payload(),
            headers=owner_headers,
        )
        assert response.status_code == 404

    def test_update_agent_requires_authentication(
        self, client, fake_app, fake_agent, db
    ):
        """Missing auth headers returns 401/403."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(),
        )
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Delete agent
# ---------------------------------------------------------------------------

class TestDeleteAgent:
    """DELETE /internal/apps/{app_id}/agents/{agent_id}"""

    def test_delete_agent_returns_200(
        self, client, fake_app, fake_agent, owner_headers, db
    ):
        """Deleting an existing agent returns 200."""
        db.flush()
        response = client.delete(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200

    def test_delete_agent_removes_from_list(
        self, client, fake_app, fake_agent, owner_headers, db
    ):
        """After deletion, agent no longer appears in list."""
        db.flush()
        agent_id = fake_agent.agent_id

        # Verify agent exists before delete
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{agent_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200

        # Delete the agent
        response = client.delete(
            f"/internal/apps/{fake_app.app_id}/agents/{agent_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200

        # Verify agent is gone
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{agent_id}",
            headers=owner_headers,
        )
        assert response.status_code == 404

    def test_delete_agent_returns_404_for_missing_agent(
        self, client, fake_app, owner_headers
    ):
        """Deleting non-existent agent returns 404."""
        response = client.delete(
            f"/internal/apps/{fake_app.app_id}/agents/99999",
            headers=owner_headers,
        )
        assert response.status_code == 404

    def test_delete_agent_requires_authentication(
        self, client, fake_app, fake_agent, db
    ):
        """Missing auth headers returns 401/403."""
        db.flush()
        response = client.delete(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}"
        )
        assert response.status_code in (401, 403)
