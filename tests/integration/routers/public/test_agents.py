"""
Integration tests for public API agents endpoints.

Uses the shared test infrastructure (TestClient, transactional DB, real API key).
Only the AgentService write operations are tested via the real DB — no LLM calls.
"""

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def agents_url(app_id: int, agent_id: int = None) -> str:
    base = f"/public/v1/app/{app_id}/agents"
    if agent_id is not None:
        return f"{base}/{agent_id}"
    return base


def api_headers(key: str) -> dict:
    return {"X-API-KEY": key}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAgentAuth:
    def test_no_api_key_returns_401(self, client, fake_app):
        resp = client.get(agents_url(fake_app.app_id))
        assert resp.status_code == 401

    def test_invalid_api_key_returns_401(self, client, fake_app):
        resp = client.get(
            agents_url(fake_app.app_id),
            headers=api_headers("totally-invalid-key"),
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# List agents
# ---------------------------------------------------------------------------


class TestListAgents:
    def test_returns_200_with_agents(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        resp = client.get(
            agents_url(fake_app.app_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert len(data["agents"]) >= 1

        agent_data = data["agents"][0]
        assert "agent_id" in agent_data
        assert "name" in agent_data
        assert "type" in agent_data
        assert "is_tool" in agent_data
        assert "request_count" in agent_data

    def test_empty_app_returns_empty_list(
        self, client, fake_app, fake_api_key, db
    ):
        """App with no agents returns empty list."""
        from models.agent import Agent

        db.query(Agent).filter(Agent.app_id == fake_app.app_id).delete()
        db.flush()

        resp = client.get(
            agents_url(fake_app.app_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert resp.json()["agents"] == []


# ---------------------------------------------------------------------------
# Get agent
# ---------------------------------------------------------------------------


class TestGetAgent:
    def test_returns_200_with_detail(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        resp = client.get(
            agents_url(fake_app.app_id, fake_agent.agent_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "agent" in data
        agent = data["agent"]
        assert agent["agent_id"] == fake_agent.agent_id
        assert agent["name"] == fake_agent.name
        # Detail schema includes extra fields
        assert "system_prompt" in agent
        assert "temperature" in agent

    def test_nonexistent_agent_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        resp = client.get(
            agents_url(fake_app.app_id, 999999),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_agent_from_other_app_returns_404(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        """Accessing an agent via a different app_id should return 404 (IDOR protection)."""
        other_app_id = fake_app.app_id + 1000
        resp = client.get(
            agents_url(other_app_id, fake_agent.agent_id),
            headers=api_headers(fake_api_key.key),
        )
        # Either 404 (agent not in app) or 401/403 (key not valid for other app)
        assert resp.status_code in (401, 403, 404)


# ---------------------------------------------------------------------------
# Create agent
# ---------------------------------------------------------------------------


class TestCreateAgent:
    def test_create_agent_returns_201(
        self, client, fake_app, fake_api_key, fake_ai_service, db
    ):
        payload = {
            "name": "Integration Test Agent",
            "type": "agent",
            "description": "Created by integration test",
            "service_id": fake_ai_service.service_id,
        }
        resp = client.post(
            agents_url(fake_app.app_id),
            json=payload,
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "agent" in data
        assert data["agent"]["name"] == "Integration Test Agent"
        assert data["agent"]["agent_id"] is not None

    def test_missing_name_returns_422(
        self, client, fake_app, fake_api_key, db
    ):
        """Pydantic validation rejects missing required field."""
        payload = {"description": "No name provided"}
        resp = client.post(
            agents_url(fake_app.app_id),
            json=payload,
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Update agent
# ---------------------------------------------------------------------------


class TestUpdateAgent:
    def test_update_agent_returns_200(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        payload = {"name": "Updated Agent Name"}
        resp = client.put(
            agents_url(fake_app.app_id, fake_agent.agent_id),
            json=payload,
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert resp.json()["agent"]["name"] == "Updated Agent Name"

    def test_update_nonexistent_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        payload = {"name": "Ghost"}
        resp = client.put(
            agents_url(fake_app.app_id, 999999),
            json=payload,
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete agent
# ---------------------------------------------------------------------------


class TestDeleteAgent:
    def test_delete_agent_returns_204(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        resp = client.delete(
            agents_url(fake_app.app_id, fake_agent.agent_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 204

    def test_delete_nonexistent_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        resp = client.delete(
            agents_url(fake_app.app_id, 999999),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404
