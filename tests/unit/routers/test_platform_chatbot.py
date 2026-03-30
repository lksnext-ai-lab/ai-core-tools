"""
Unit tests for the platform chatbot internal router.
All dependencies are mocked — no DB or LLM required.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from routers.internal import platform_chatbot as chatbot_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    return MagicMock()


def _make_user():
    user = MagicMock()
    user.identity.id = "42"
    user.identity.email = "test@example.com"
    return user


def _mock_settings(mocker, agent_id):
    """Patch SystemSettingsService so get_setting returns agent_id."""
    mock_cls = mocker.patch.object(chatbot_module, "SystemSettingsService")
    instance = mock_cls.return_value
    instance.get_setting.return_value = agent_id
    return instance


def _mock_agent_service(mocker, agent=None):
    """Patch AgentService so get_agent returns agent (or None)."""
    mock_cls = mocker.patch.object(chatbot_module, "AgentService")
    instance = mock_cls.return_value
    if agent is None:
        instance.get_agent.return_value = None
    else:
        instance.get_agent.return_value = agent
    return instance


def _make_agent(agent_id=42, name="My Bot", description="Help", app_id=1):
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.name = name
    agent.description = description
    agent.app_id = app_id
    return agent


def _mock_execution_service(mocker, result=None):
    """Patch AgentExecutionService so execute_agent_chat_with_file_refs is an AsyncMock."""
    mock_cls = mocker.patch.object(chatbot_module, "AgentExecutionService")
    instance = mock_cls.return_value
    if result is None:
        result = {
            "response": "Hello!",
            "agent_id": 42,
            "conversation_id": 1,
            "metadata": {"tokens": 10},
        }
    instance.execute_agent_chat_with_file_refs = AsyncMock(return_value=result)
    return instance


def _mock_streaming_service(mocker):
    """Patch AgentStreamingService so stream_agent_chat returns an async generator."""
    mock_cls = mocker.patch.object(chatbot_module, "AgentStreamingService")
    instance = mock_cls.return_value

    async def _gen():
        yield 'data: {"type":"token","content":"hi"}\n\n'

    instance.stream_agent_chat.return_value = _gen()
    return instance


# ---------------------------------------------------------------------------
# TestPlatformChatbotConfig
# ---------------------------------------------------------------------------

class TestPlatformChatbotConfig:
    @pytest.mark.asyncio
    async def test_config_returns_disabled_when_agent_id_is_negative_one(self, mocker):
        _mock_settings(mocker, -1)
        response = await chatbot_module.get_platform_chatbot_config(
            db=_make_db(),
            current_user=_make_user(),
        )
        assert response.enabled is False
        assert response.agent_name is None

    @pytest.mark.asyncio
    async def test_config_returns_disabled_when_agent_not_found(self, mocker):
        _mock_settings(mocker, 42)
        _mock_agent_service(mocker, agent=None)
        response = await chatbot_module.get_platform_chatbot_config(
            db=_make_db(),
            current_user=_make_user(),
        )
        assert response.enabled is False
        assert response.agent_name is None

    @pytest.mark.asyncio
    async def test_config_returns_enabled_with_agent_metadata(self, mocker):
        _mock_settings(mocker, 42)
        _mock_agent_service(mocker, agent=_make_agent(name="My Bot", description="Help"))
        response = await chatbot_module.get_platform_chatbot_config(
            db=_make_db(),
            current_user=_make_user(),
        )
        assert response.enabled is True
        assert response.agent_name == "My Bot"
        assert response.agent_description == "Help"

    @pytest.mark.asyncio
    async def test_config_does_not_expose_agent_id_or_app_id(self, mocker):
        _mock_settings(mocker, 42)
        _mock_agent_service(mocker, agent=_make_agent(name="My Bot", description="Help"))
        response = await chatbot_module.get_platform_chatbot_config(
            db=_make_db(),
            current_user=_make_user(),
        )
        # PlatformChatbotConfigResponse should not have agent_id or app_id fields
        assert "agent_id" not in response.model_fields
        assert "app_id" not in response.model_fields


# ---------------------------------------------------------------------------
# TestPlatformChatbotChat
# ---------------------------------------------------------------------------

class TestPlatformChatbotChat:
    @pytest.mark.asyncio
    async def test_chat_returns_404_when_disabled(self, mocker):
        _mock_settings(mocker, -1)
        body = MagicMock()
        body.message = "hello"
        body.session_id = "s1"

        with pytest.raises(HTTPException) as exc_info:
            await chatbot_module.platform_chatbot_chat(
                body=body,
                db=_make_db(),
                current_user=_make_user(),
            )
        assert exc_info.value.status_code == 404
        assert "not configured" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_chat_returns_404_when_agent_not_found(self, mocker):
        _mock_settings(mocker, 42)
        _mock_agent_service(mocker, agent=None)
        body = MagicMock()
        body.message = "hello"
        body.session_id = "s1"

        with pytest.raises(HTTPException) as exc_info:
            await chatbot_module.platform_chatbot_chat(
                body=body,
                db=_make_db(),
                current_user=_make_user(),
            )
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_chat_delegates_to_execution_service(self, mocker):
        _mock_settings(mocker, 42)
        _mock_agent_service(mocker, agent=_make_agent(agent_id=42))
        svc = _mock_execution_service(mocker)
        body = MagicMock()
        body.message = "hello"
        body.session_id = "s1"

        result = await chatbot_module.platform_chatbot_chat(
            body=body,
            db=_make_db(),
            current_user=_make_user(),
        )

        call_kwargs = svc.execute_agent_chat_with_file_refs.call_args
        assert call_kwargs.kwargs["agent_id"] == 42
        assert call_kwargs.kwargs["message"] == "hello"
        assert call_kwargs.kwargs["file_references"] is None
        assert call_kwargs.kwargs["conversation_id"] is None

    @pytest.mark.asyncio
    async def test_chat_returns_503_when_execution_raises(self, mocker):
        _mock_settings(mocker, 42)
        _mock_agent_service(mocker, agent=_make_agent(agent_id=42))
        svc = _mock_execution_service(mocker)
        svc.execute_agent_chat_with_file_refs = AsyncMock(
            side_effect=RuntimeError("LLM timeout")
        )
        body = MagicMock()
        body.message = "hello"
        body.session_id = "s1"

        with pytest.raises(HTTPException) as exc_info:
            await chatbot_module.platform_chatbot_chat(
                body=body,
                db=_make_db(),
                current_user=_make_user(),
            )
        assert exc_info.value.status_code == 503
