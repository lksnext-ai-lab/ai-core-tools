"""
Security tests for agent endpoints authorization (BOLA/IDOR prevention).

Validates:
  - Users without a role on an app cannot access its agents (playground, chat, etc.)
  - Agent-to-app ownership is enforced (can't operate on agent from another app)
  - Role requirements are enforced on previously unprotected endpoints
"""

import pytest
from datetime import datetime

from tests.factories import (
    configure_factories,
    UserFactory,
    AppFactory,
    AIServiceFactory,
    AgentFactory,
    AppCollaboratorFactory,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def setup_cross_app(db, fake_user, fake_app, fake_agent):
    """
    Create a second app with its own agent, owned by a different user.
    Returns (other_app, other_agent, other_user).
    """
    configure_factories(db)
    other_user = UserFactory(email="other@mattin-test.com", name="Other User")
    other_app = AppFactory(owner=other_user)
    other_service = AIServiceFactory(app=other_app)
    other_agent = AgentFactory(app=other_app, ai_service=other_service)
    db.flush()
    return other_app, other_agent, other_user


@pytest.fixture
def unrelated_user_headers(db, client, setup_cross_app):
    """Auth headers for a user who has NO role on the main fake_app."""
    _, _, other_user = setup_cross_app
    db.flush()
    response = client.post(
        "/internal/auth/dev-login",
        json={"email": other_user.email},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test: require_min_role enforced on playground
# ---------------------------------------------------------------------------

class TestPlaygroundAuthorization:
    """GET /internal/apps/{app_id}/agents/{agent_id}/playground"""

    def test_playground_requires_role(
        self, client, fake_app, fake_agent, unrelated_user_headers, db
    ):
        """User without role on app gets 403 when accessing playground."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/playground",
            headers=unrelated_user_headers,
        )
        assert response.status_code == 403

    def test_playground_accessible_by_viewer(
        self, client, fake_app, fake_agent, owner_headers, db
    ):
        """Owner can access playground."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/playground",
            headers=owner_headers,
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test: require_min_role enforced on analytics
# ---------------------------------------------------------------------------

class TestAnalyticsAuthorization:
    """GET /internal/apps/{app_id}/agents/{agent_id}/analytics"""

    def test_analytics_requires_role(
        self, client, fake_app, fake_agent, unrelated_user_headers, db
    ):
        """User without role on app gets 403 when accessing analytics."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/analytics",
            headers=unrelated_user_headers,
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Test: agent-to-app ownership on delete
# ---------------------------------------------------------------------------

class TestDeleteAgentCrossApp:
    """DELETE /internal/apps/{app_id}/agents/{agent_id}"""

    def test_delete_agent_from_wrong_app_returns_404(
        self, client, fake_app, owner_headers, setup_cross_app, db
    ):
        """
        An owner of App A cannot delete an agent that belongs to App B,
        even if they pass App A's app_id (which passes the role check).
        """
        _, other_agent, _ = setup_cross_app
        db.flush()
        response = client.delete(
            f"/internal/apps/{fake_app.app_id}/agents/{other_agent.agent_id}",
            headers=owner_headers,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test: agent-to-app ownership on MCP usage
# ---------------------------------------------------------------------------

class TestMCPUsageCrossApp:
    """GET /internal/apps/{app_id}/agents/{agent_id}/mcp-usage"""

    def test_mcp_usage_from_wrong_app_returns_404(
        self, client, fake_app, owner_headers, setup_cross_app, db
    ):
        """Cannot get MCP usage for an agent from another app."""
        _, other_agent, _ = setup_cross_app
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{other_agent.agent_id}/mcp-usage",
            headers=owner_headers,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test: require_min_role enforced on update-prompt
# ---------------------------------------------------------------------------

class TestUpdatePromptAuthorization:
    """POST /internal/apps/{app_id}/agents/{agent_id}/update-prompt"""

    def test_update_prompt_requires_editor_role(
        self, client, fake_app, fake_agent, unrelated_user_headers, db
    ):
        """User without role cannot update agent prompt."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/update-prompt",
            json={"type": "system", "prompt": "hacked prompt"},
            headers=unrelated_user_headers,
        )
        assert response.status_code == 403

    def test_update_prompt_cross_app_returns_404(
        self, client, fake_app, owner_headers, setup_cross_app, db
    ):
        """Cannot update prompt for an agent from another app."""
        _, other_agent, _ = setup_cross_app
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{other_agent.agent_id}/update-prompt",
            json={"type": "system", "prompt": "hacked prompt"},
            headers=owner_headers,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test: require_min_role enforced on conversation endpoints
# ---------------------------------------------------------------------------

class TestConversationAuthorization:
    """Conversation-related endpoints require viewer role."""

    def test_reset_conversation_requires_role(
        self, client, fake_app, fake_agent, unrelated_user_headers, db
    ):
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/reset",
            headers=unrelated_user_headers,
        )
        assert response.status_code == 403

    def test_conversation_history_requires_role(
        self, client, fake_app, fake_agent, unrelated_user_headers, db
    ):
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/conversation-history",
            headers=unrelated_user_headers,
        )
        assert response.status_code == 403

    def test_list_files_requires_role(
        self, client, fake_app, fake_agent, unrelated_user_headers, db
    ):
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/files",
            headers=unrelated_user_headers,
        )
        assert response.status_code == 403

    def test_download_file_requires_role(
        self, client, fake_app, fake_agent, unrelated_user_headers, db
    ):
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}/files/some-file-id/download",
            headers=unrelated_user_headers,
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Test: playground cross-app IDOR
# ---------------------------------------------------------------------------

class TestPlaygroundCrossApp:
    """Verify user can't access playground of agent from another app via URL."""

    def test_playground_cross_app_returns_403(
        self, client, fake_app, fake_agent, setup_cross_app, auth_headers, db
    ):
        """
        auth_headers user (fake_user) has no role on other_app,
        so accessing other_app's agent playground should return 403.
        """
        other_app, other_agent, _ = setup_cross_app
        db.flush()
        response = client.get(
            f"/internal/apps/{other_app.app_id}/agents/{other_agent.agent_id}/playground",
            headers=auth_headers,
        )
        assert response.status_code == 403
