"""
Tests for public API openai router.
"""
import base64
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from routers.public.v1 import openai as openai_module
from routers.public.v1.schemas_openai import OpenAIChatCompletionRequest, OpenAIMessage
from models.app import App


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_auth(mocker):
    mocker.patch.object(openai_module, "validate_api_key_for_app", return_value=None)


def _mock_app(mocker):
    # Mock get_app_by_identifier
    app = App(app_id=1, name="Test App", slug="test-app", enable_openai_api=True)
    mocker.patch.object(openai_module, "get_app_by_identifier", return_value=app)
    return app


def _mock_agent_service(mocker, has_memory=False, agent_id=1):
    mock_cls = mocker.patch.object(openai_module, "AgentService")
    svc = mock_cls.return_value
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.app_id = 1
    agent.has_memory = has_memory
    agent.create_date = MagicMock()
    agent.create_date.timestamp.return_value = 1600000000
    svc.get_agent.return_value = agent
    svc.get_agents.return_value = [agent]
    return svc


def _mock_execution_service(mocker, result=None):
    mock_cls = mocker.patch.object(openai_module, "AgentExecutionService")
    svc = mock_cls.return_value
    if result is None:
        result = {
            "response": "Hello from OpenAI compatible API",
            "conversation_id": None,
            "metadata": {"usage": {"prompt_tokens": 10, "completion_tokens": 20}},
        }
    svc.execute_agent_chat_with_file_refs = AsyncMock(return_value=result)
    return svc

def _mock_file_management_service(mocker):
    mock_cls = mocker.patch.object(openai_module, "FileManagementService")
    svc = mock_cls.return_value
    file_ref_mock = MagicMock()
    file_ref_mock.file_id = "mocked-file-id"
    svc.upload_file = AsyncMock(return_value=file_ref_mock)
    return svc


class TestOpenAIRouter:
    @pytest.mark.asyncio
    async def test_chat_completions_string_content(self, mocker):
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)
        
        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[OpenAIMessage(role="user", content="Hello")]
        )
        
        result = await openai_module.chat_completions(
            app_identifier="1",
            request=req,
            api_key="key",
            db=MagicMock()
        )
        
        assert result.object == "chat.completion"
        assert result.choices[0].message.content == "Hello from OpenAI compatible API"
        exec_mock.execute_agent_chat_with_file_refs.assert_called_once()
        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert kwargs["message"] == "[Latest Input]\nuser: Hello"
        assert kwargs["file_references"] == []

    @pytest.mark.asyncio
    async def test_chat_completions_multipart_content_base64(self, mocker):
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)
        file_mock = _mock_file_management_service(mocker)
        
        # 1x1 png base64
        b64_img = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        
        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[
                OpenAIMessage(
                    role="user", 
                    content=[
                        {"type": "text", "text": "What is this?"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}}
                    ]
                )
            ]
        )
        
        result = await openai_module.chat_completions(
            app_identifier="1",
            request=req,
            api_key="key",
            db=MagicMock()
        )
        
        assert result.object == "chat.completion"
        
        file_mock.upload_file.assert_called_once()
        exec_mock.execute_agent_chat_with_file_refs.assert_called_once()
        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert kwargs["message"] == "[Latest Input]\nuser: What is this?"
        assert len(kwargs["file_references"]) == 1
        assert kwargs["file_references"][0].file_id == "mocked-file-id"

    @pytest.mark.asyncio
    async def test_chat_completions_multipart_content_url(self, mocker):
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)
        file_mock = _mock_file_management_service(mocker)
        
        # Mock httpx
        mock_resp = MagicMock()
        mock_resp.content = b"fake-image-bytes"
        mock_resp.headers = {"content-type": "image/jpeg"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        mocker.patch("httpx.AsyncClient", return_value=mock_client)
        
        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[
                OpenAIMessage(
                    role="user", 
                    content=[
                        {"type": "text", "text": "What is this?"},
                        {"type": "image_url", "image_url": {"url": "http://example.com/image.jpg"}}
                    ]
                )
            ]
        )
        
        result = await openai_module.chat_completions(
            app_identifier="1",
            request=req,
            api_key="key",
            db=MagicMock()
        )
        
        assert result.object == "chat.completion"
        
        mock_client.get.assert_called_once_with("http://example.com/image.jpg", timeout=10.0)
        file_mock.upload_file.assert_called_once()
        
        exec_mock.execute_agent_chat_with_file_refs.assert_called_once()
        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert kwargs["message"] == "[Latest Input]\nuser: What is this?"
        assert len(kwargs["file_references"]) == 1

    @pytest.mark.asyncio
    async def test_chat_completions_with_history_and_system(self, mocker):
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)
        
        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[
                OpenAIMessage(role="system", content="You are an AI."),
                OpenAIMessage(role="user", content="Hi"),
                OpenAIMessage(role="assistant", content="Hello there!"),
                OpenAIMessage(role="user", content="How are you?")
            ]
        )
        
        result = await openai_module.chat_completions(
            app_identifier="1",
            request=req,
            api_key="key",
            db=MagicMock()
        )
        
        assert result.object == "chat.completion"
        exec_mock.execute_agent_chat_with_file_refs.assert_called_once()
        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        
        expected_message = (
            "--- Conversation History ---\n"
            "user: Hi\n\n"
            "assistant: Hello there!\n"
            "--- End of History ---\n\n"
            "[Latest Input]\n"
            "user: How are you?"
        )
        
        assert kwargs["message"] == expected_message
