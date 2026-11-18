"""
Regression tests for Fix A: agent create/update must not accept another tenant's
resource ids (service_id, silo_id, output_parser_id, vision/transcription/video AI
service ids, media_embedding_service_id, tool_ids, mcp_config_ids).

Bug: AgentService.create_or_update_agent (and update_agent_tools / update_agent_mcps)
persisted whatever foreign-key ids the caller supplied without checking that they
belonged to the target app, letting an editor of App A point their agent at App B's
AI service / silo / output parser / tool-agent / MCP config (IDOR, resource hijack
+ possible credential/quota abuse).

These tests use two separate Apps (``fake_app`` = App A, ``other_app`` = App B, both
owned by the same ``fake_user`` so app-level RBAC on App A always passes) to isolate
the assertions to the resource-ownership check under test.
"""

import pytest

from tests.factories import (
    AppFactory,
    AgentFactory,
    AIServiceFactory,
    SiloFactory,
    configure_factories,
)


def _editor_headers(fake_user, owner_headers):
    fake_user.platform_role = "editor"
    return owner_headers


@pytest.fixture
def other_app(db, fake_user):
    """A second App (App B), owned by the same user as fake_app (App A)."""
    configure_factories(db)
    return AppFactory(owner_id=fake_user.user_id)


def _create_payload(**overrides) -> dict:
    payload = {
        "name": "Cross-tenant probe agent",
        "description": "",
        "system_prompt": "test",
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
        "vision_service_id": None,
        "vision_system_prompt": "",
        "text_system_prompt": "",
    }
    payload.update(overrides)
    return payload


class TestServiceIdScoping:
    def test_rejects_service_id_from_another_app(
        self, client, fake_app, other_app, fake_user, owner_headers, db
    ):
        configure_factories(db)
        headers = _editor_headers(fake_user, owner_headers)
        other_service = AIServiceFactory(app=other_app)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=_create_payload(service_id=other_service.service_id),
            headers=headers,
        )
        assert response.status_code == 400

    def test_accepts_service_id_from_the_same_app(
        self, client, fake_app, fake_ai_service, fake_user, owner_headers, db
    ):
        headers = _editor_headers(fake_user, owner_headers)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=_create_payload(service_id=fake_ai_service.service_id),
            headers=headers,
        )
        assert response.status_code in (200, 201)
        assert response.json()["service_id"] == fake_ai_service.service_id

    def test_accepts_system_wide_service_id(
        self, client, fake_app, fake_user, owner_headers, db
    ):
        """A service_id with app_id=None (system/platform AI service) is allowed for any app."""
        from models.ai_service import AIService

        headers = _editor_headers(fake_user, owner_headers)
        system_service = AIService(
            name="System OpenAI",
            provider="OpenAI",
            api_key="sk-system-key",  # pragma: allowlist secret
            app_id=None,
        )
        db.add(system_service)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=_create_payload(service_id=system_service.service_id),
            headers=headers,
        )
        assert response.status_code in (200, 201)
        assert response.json()["service_id"] == system_service.service_id


class TestSiloIdScoping:
    def test_rejects_silo_id_from_another_app(
        self, client, fake_app, other_app, fake_user, owner_headers, db
    ):
        configure_factories(db)
        headers = _editor_headers(fake_user, owner_headers)
        other_silo = SiloFactory(app=other_app)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=_create_payload(silo_id=other_silo.silo_id),
            headers=headers,
        )
        assert response.status_code == 400

    def test_accepts_silo_id_from_the_same_app(
        self, client, fake_app, fake_user, owner_headers, db
    ):
        configure_factories(db)
        headers = _editor_headers(fake_user, owner_headers)
        same_app_silo = SiloFactory(app=fake_app)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=_create_payload(silo_id=same_app_silo.silo_id),
            headers=headers,
        )
        assert response.status_code in (200, 201)
        assert response.json()["silo_id"] == same_app_silo.silo_id


class TestOutputParserIdScoping:
    def test_rejects_output_parser_id_from_another_app(
        self, client, fake_app, other_app, fake_user, owner_headers, db
    ):
        from models.output_parser import OutputParser

        headers = _editor_headers(fake_user, owner_headers)
        other_parser = OutputParser(name="Other app's parser", app_id=other_app.app_id, fields=[])
        db.add(other_parser)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=_create_payload(output_parser_id=other_parser.parser_id),
            headers=headers,
        )
        assert response.status_code == 400

    def test_accepts_output_parser_id_from_the_same_app(
        self, client, fake_app, fake_user, owner_headers, db
    ):
        from models.output_parser import OutputParser

        headers = _editor_headers(fake_user, owner_headers)
        same_app_parser = OutputParser(name="Same app's parser", app_id=fake_app.app_id, fields=[])
        db.add(same_app_parser)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=_create_payload(output_parser_id=same_app_parser.parser_id),
            headers=headers,
        )
        assert response.status_code in (200, 201)
        assert response.json()["output_parser_id"] == same_app_parser.parser_id


class TestMediaEmbeddingServiceIdScoping:
    def test_rejects_media_embedding_service_id_from_another_app(
        self, client, fake_app, other_app, fake_user, owner_headers, db
    ):
        from models.embedding_service import EmbeddingService

        headers = _editor_headers(fake_user, owner_headers)
        other_embedding = EmbeddingService(
            name="Other app's embedding service", provider="OpenAI", app_id=other_app.app_id
        )
        db.add(other_embedding)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=_create_payload(media_embedding_service_id=other_embedding.service_id),
            headers=headers,
        )
        assert response.status_code == 400

    def test_accepts_system_wide_media_embedding_service_id(
        self, client, fake_app, fake_user, owner_headers, db
    ):
        from models.embedding_service import EmbeddingService

        headers = _editor_headers(fake_user, owner_headers)
        system_embedding = EmbeddingService(
            name="System embedding service", provider="OpenAI", app_id=None
        )
        db.add(system_embedding)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=_create_payload(media_embedding_service_id=system_embedding.service_id),
            headers=headers,
        )
        assert response.status_code in (200, 201)
        assert response.json()["media_embedding_service_id"] == system_embedding.service_id


class TestToolIdsScoping:
    def test_drops_tool_id_from_another_app(
        self, client, fake_app, other_app, fake_user, owner_headers, db
    ):
        """A tool-agent belonging to another app is silently dropped, not attached."""
        configure_factories(db)
        headers = _editor_headers(fake_user, owner_headers)
        other_service = AIServiceFactory(app=other_app)
        other_tool_agent = AgentFactory(app=other_app, ai_service=other_service, is_tool=True)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=_create_payload(tool_ids=[other_tool_agent.agent_id]),
            headers=headers,
        )
        assert response.status_code in (200, 201)
        assert other_tool_agent.agent_id not in response.json()["tool_ids"]

    def test_accepts_tool_id_from_the_same_app(
        self, client, fake_app, fake_ai_service, fake_user, owner_headers, db
    ):
        configure_factories(db)
        headers = _editor_headers(fake_user, owner_headers)
        same_app_tool_agent = AgentFactory(app=fake_app, ai_service=fake_ai_service, is_tool=True)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=_create_payload(tool_ids=[same_app_tool_agent.agent_id]),
            headers=headers,
        )
        assert response.status_code in (200, 201)
        assert same_app_tool_agent.agent_id in response.json()["tool_ids"]


class TestMcpConfigIdsScoping:
    def test_drops_mcp_config_id_from_another_app(
        self, client, fake_app, other_app, fake_user, owner_headers, db
    ):
        from models.mcp_config import MCPConfig

        headers = _editor_headers(fake_user, owner_headers)
        other_mcp = MCPConfig(
            name="Other app's MCP",
            config={"transport": "stdio", "command": "echo"},
            app_id=other_app.app_id,
        )
        db.add(other_mcp)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=_create_payload(mcp_config_ids=[other_mcp.config_id]),
            headers=headers,
        )
        assert response.status_code in (200, 201)
        assert other_mcp.config_id not in response.json()["mcp_config_ids"]

    def test_accepts_mcp_config_id_from_the_same_app(
        self, client, fake_app, fake_user, owner_headers, db
    ):
        from models.mcp_config import MCPConfig

        headers = _editor_headers(fake_user, owner_headers)
        same_app_mcp = MCPConfig(
            name="Same app's MCP",
            config={"transport": "stdio", "command": "echo"},
            app_id=fake_app.app_id,
        )
        db.add(same_app_mcp)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/agents/0",
            json=_create_payload(mcp_config_ids=[same_app_mcp.config_id]),
            headers=headers,
        )
        assert response.status_code in (200, 201)
        assert same_app_mcp.config_id in response.json()["mcp_config_ids"]
