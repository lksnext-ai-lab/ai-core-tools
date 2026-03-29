"""
Integration tests for the platform chatbot internal router.
Tests run against the real test PostgreSQL DB (via conftest fixtures).

Endpoints under test:
  GET  /internal/platform-chatbot/config
  POST /internal/platform-chatbot/chat
"""
import pytest


# ---------------------------------------------------------------------------
# TestPlatformChatbotAuth
# ---------------------------------------------------------------------------


class TestPlatformChatbotAuth:
    def test_config_requires_auth(self, client):
        response = client.get("/internal/platform-chatbot/config")
        assert response.status_code == 401

    def test_chat_requires_auth(self, client):
        response = client.post(
            "/internal/platform-chatbot/chat",
            json={"message": "hi", "session_id": "s1"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# TestPlatformChatbotConfig
# ---------------------------------------------------------------------------


class TestPlatformChatbotConfig:
    def test_config_returns_disabled_when_default(self, client, auth_headers):
        """Default setting is -1 so chatbot is disabled."""
        response = client.get(
            "/internal/platform-chatbot/config",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False

    def test_config_returns_disabled_when_agent_id_set_but_agent_deleted(
        self, client, auth_headers, db, monkeypatch
    ):
        """Non-existent agent ID leads to enabled=False."""
        monkeypatch.setattr(
            "services.system_settings_service.SystemSettingsService.get_setting",
            lambda self, key: 99999 if key == "platform_chatbot_agent_id" else None,
        )
        response = client.get(
            "/internal/platform-chatbot/config",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_config_returns_enabled_when_agent_configured(
        self, client, auth_headers, db, fake_agent, monkeypatch
    ):
        """When a real agent is configured, the endpoint returns enabled=True."""
        monkeypatch.setattr(
            "services.system_settings_service.SystemSettingsService.get_setting",
            lambda self, key: fake_agent.agent_id if key == "platform_chatbot_agent_id" else None,
        )
        response = client.get(
            "/internal/platform-chatbot/config",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["agent_name"] == fake_agent.name


# ---------------------------------------------------------------------------
# TestPlatformChatbotChat
# ---------------------------------------------------------------------------


class TestPlatformChatbotChat:
    def test_chat_returns_404_when_not_configured(self, client, auth_headers):
        """Default setting -1 → 404."""
        response = client.post(
            "/internal/platform-chatbot/chat",
            json={"message": "hi", "session_id": "s1"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_chat_returns_404_when_agent_missing(
        self, client, auth_headers, monkeypatch
    ):
        """Agent ID set to non-existent value → 404."""
        monkeypatch.setattr(
            "services.system_settings_service.SystemSettingsService.get_setting",
            lambda self, key: 99999 if key == "platform_chatbot_agent_id" else None,
        )
        response = client.post(
            "/internal/platform-chatbot/chat",
            json={"message": "hi", "session_id": "s1"},
            headers=auth_headers,
        )
        assert response.status_code == 404
