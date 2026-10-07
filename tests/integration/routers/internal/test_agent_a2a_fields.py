"""Integration tests for A2A fields on the internal agent API (step_009, FR-3, AC-40).

Endpoint under test:
  POST /internal/apps/{app_id}/agents/{agent_id}  (create/update, carries the fields)
  GET  /internal/apps/{app_id}/agents/{agent_id}   (returns them, plus a2a_card_url/a2a_rpc_url)
  GET  /internal/apps/{app_id}/agents               (list item carries a2a_enabled)

Covers:
  - an EDITOR/OWNER update persists the A2A fields and GET returns them with URLs;
  - VIEWER on the same app gets 403 on update (AC-40);
  - values beyond the caps are rejected with 422 (AC-40);
  - the list endpoint surfaces a2a_enabled.
"""

import pytest
from datetime import datetime

from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from tests.factories import configure_factories, UserFactory


def agent_payload(**overrides) -> dict:
    """Minimal valid create/update payload, overridable with A2A fields."""
    payload = {
        "name": "A2A Test Agent",
        "description": "Agent for A2A field tests",
        "system_prompt": "You are a helpful test assistant.",
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
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def viewer_headers(db, fake_app, fake_user):
    """Auth headers for a VIEWER on fake_app."""
    from utils.local_auth_tokens import mint_access_token

    configure_factories(db)
    # platform_role='editor' bypasses the unrelated global require_editor_for_writes
    # guard (platform_role defaults to 'viewer'), so this test exercises only the
    # app-level RBAC (require_min_role("editor")) under AC-40.
    viewer_user = UserFactory(
        email="viewer-a2a@mattin-test.com", name="Viewer User", platform_role="editor"
    )
    collab = AppCollaborator(
        app_id=fake_app.app_id,
        user_id=viewer_user.user_id,
        role=CollaborationRole.VIEWER,
        status=CollaborationStatus.ACCEPTED,
        invited_by=fake_user.user_id,
        invited_at=datetime.now(),
        accepted_at=datetime.now(),
    )
    db.add(collab)
    db.flush()
    token, _ = mint_access_token(viewer_user.user_id, viewer_user.email, viewer_user.name)
    return {"Authorization": f"Bearer {token}"}


class TestUpdateAgentA2AFields:
    """POST /internal/apps/{app_id}/agents/{agent_id}"""

    def test_owner_update_persists_a2a_fields(
        self, client, fake_app, fake_agent, fake_user, owner_headers, db
    ):
        # platform_role='editor' bypasses the unrelated global require_editor_for_writes
        # guard (platform_role defaults to 'viewer').
        fake_user.platform_role = 'editor'
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(
                service_id=fake_agent.service_id,
                a2a_enabled=True,
                a2a_card_visibility="api_key",
                a2a_name_override="  Support Bot  ",
                a2a_description_override="  Handles billing questions  ",
                a2a_skill_tags=["Billing", "billing", " support "],
                a2a_examples=["  How do I pay my invoice?  ", ""],
            ),
            headers=owner_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["a2a_enabled"] is True
        assert body["a2a_card_visibility"] == "api_key"
        assert body["a2a_name_override"] == "Support Bot"
        assert body["a2a_description_override"] == "Handles billing questions"
        assert body["a2a_skill_tags"] == ["Billing", "support"]
        assert body["a2a_examples"] == ["How do I pay my invoice?"]

    def test_get_after_update_returns_persisted_fields_and_urls(
        self, client, fake_app, fake_agent, fake_user, owner_headers, db, monkeypatch
    ):
        monkeypatch.setenv("A2A_PUBLIC_BASE_URL", "https://ai.example.com")
        from utils import a2a_config
        a2a_config.get_a2a_config.cache_clear()

        fake_user.platform_role = 'editor'
        db.flush()
        client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(service_id=fake_agent.service_id, a2a_enabled=True),
            headers=owner_headers,
        )

        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["a2a_enabled"] is True
        assert body["a2a_card_url"] == (
            f"https://ai.example.com/a2a/v1/apps/{fake_app.slug}/agents/"
            f"{fake_agent.agent_id}/.well-known/agent-card.json"
        )
        assert body["a2a_rpc_url"] == (
            f"https://ai.example.com/a2a/v1/apps/{fake_app.slug}/agents/{fake_agent.agent_id}"
        )

        a2a_config.get_a2a_config.cache_clear()

    def test_viewer_update_returns_403(
        self, client, fake_app, fake_agent, viewer_headers, db
    ):
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(service_id=fake_agent.service_id, a2a_enabled=True),
            headers=viewer_headers,
        )
        assert response.status_code == 403

    def test_over_cap_skill_tags_returns_422(
        self, client, fake_app, fake_agent, fake_user, owner_headers, db
    ):
        fake_user.platform_role = 'editor'
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(
                service_id=fake_agent.service_id,
                a2a_skill_tags=[f"tag{i}" for i in range(21)],
            ),
            headers=owner_headers,
        )
        assert response.status_code == 422

    def test_over_cap_name_override_returns_422(
        self, client, fake_app, fake_agent, fake_user, owner_headers, db
    ):
        fake_user.platform_role = 'editor'
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(
                service_id=fake_agent.service_id,
                a2a_name_override="x" * 256,
            ),
            headers=owner_headers,
        )
        assert response.status_code == 422

    def test_invalid_card_visibility_returns_422(
        self, client, fake_app, fake_agent, fake_user, owner_headers, db
    ):
        fake_user.platform_role = 'editor'
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(
                service_id=fake_agent.service_id,
                a2a_card_visibility="private",
            ),
            headers=owner_headers,
        )
        assert response.status_code == 422

    def test_null_card_visibility_returns_422(
        self, client, fake_app, fake_agent, fake_user, owner_headers, db
    ):
        """FR-3 has no 'unset' meaning for visibility; null must 422, not become 'public'."""
        fake_user.platform_role = 'editor'
        db.flush()
        payload = agent_payload(service_id=fake_agent.service_id)
        payload["a2a_card_visibility"] = None
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=payload,
            headers=owner_headers,
        )
        assert response.status_code == 422

    def test_update_without_a2a_fields_preserves_existing_values(
        self, client, fake_app, fake_agent, fake_user, owner_headers, db
    ):
        """An update that never mentions A2A fields must not disable A2A or reset
        visibility to 'public' — review fix for the MEDIUM finding (silent reset)."""
        fake_user.platform_role = 'editor'
        db.flush()

        # First call: explicitly turn A2A on with non-default values.
        setup = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(
                service_id=fake_agent.service_id,
                a2a_enabled=True,
                a2a_card_visibility="api_key",
                a2a_name_override="Support Bot",
                a2a_skill_tags=["billing"],
            ),
            headers=owner_headers,
        )
        assert setup.status_code == 200

        # Second call: a plain field edit that never mentions any A2A key (today's
        # frontend behavior, before step_019/020 ship the A2A tab).
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(
                service_id=fake_agent.service_id,
                name="A2A Test Agent (renamed)",
            ),
            headers=owner_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "A2A Test Agent (renamed)"
        assert body["a2a_enabled"] is True
        assert body["a2a_card_visibility"] == "api_key"
        assert body["a2a_name_override"] == "Support Bot"
        assert body["a2a_skill_tags"] == ["billing"]


class TestListAgentsA2AFlag:
    """GET /internal/apps/{app_id}/agents"""

    def test_list_surfaces_a2a_enabled(
        self, client, fake_app, fake_agent, fake_user, owner_headers, db
    ):
        fake_user.platform_role = 'editor'
        db.flush()
        client.post(
            f"/internal/apps/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=agent_payload(service_id=fake_agent.service_id, a2a_enabled=True),
            headers=owner_headers,
        )

        response = client.get(
            f"/internal/apps/{fake_app.app_id}/agents",
            headers=owner_headers,
        )
        assert response.status_code == 200
        agents = response.json()
        agent = next((a for a in agents if a["agent_id"] == fake_agent.agent_id), None)
        assert agent is not None
        assert agent["a2a_enabled"] is True
