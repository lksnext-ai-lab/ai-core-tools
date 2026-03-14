"""
Tests for public API chat router.
Covers: call_agent, call_agent_stream, reset_conversation,
        conversation CRUD, and shared helpers.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from routers.public.v1 import chat as chat_module
from routers.public.v1.auth import create_api_key_user_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_auth(mocker):
    mocker.patch.object(chat_module, "validate_api_key_for_app", return_value=None)
    mocker.patch.object(
        chat_module, "validate_agent_ownership", return_value=MagicMock()
    )


def _mock_execution_service(mocker, result=None):
    mock_cls = mocker.patch.object(chat_module, "AgentExecutionService")
    svc = mock_cls.return_value
    if result is None:
        result = {
            "response": "Hello!",
            "conversation_id": 42,
            "metadata": {"tokens": 10},
        }
    svc.execute_agent_chat_with_file_refs = AsyncMock(return_value=result)
    svc.reset_agent_conversation = AsyncMock(return_value=True)
    return svc


def _mock_streaming_service(mocker):
    mock_cls = mocker.patch.object(chat_module, "AgentStreamingService")
    svc = mock_cls.return_value

    async def _gen():
        yield "data: token\n\n"

    svc.stream_agent_chat.return_value = _gen()
    return svc


def _mock_process_files(mocker):
    return mocker.patch.object(
        chat_module, "_process_chat_files", new_callable=AsyncMock, return_value=[]
    )


# ---------------------------------------------------------------------------
# TestCreateApiKeyUserContext
# ---------------------------------------------------------------------------

class TestCreateApiKeyUserContext:
    def test_consistent_hash(self):
        ctx1 = create_api_key_user_context(1, "my-api-key")
        ctx2 = create_api_key_user_context(1, "my-api-key")
        assert ctx1["user_id"] == ctx2["user_id"]
        assert ctx1["user_id"].startswith("apikey_")

    def test_different_keys_different_hash(self):
        ctx1 = create_api_key_user_context(1, "key-a")
        ctx2 = create_api_key_user_context(1, "key-b")
        assert ctx1["user_id"] != ctx2["user_id"]

    def test_conversation_id_included_when_provided(self):
        ctx = create_api_key_user_context(1, "key", conversation_id="123")
        assert ctx["conversation_id"] == "123"

    def test_conversation_id_absent_when_none(self):
        ctx = create_api_key_user_context(1, "key")
        assert "conversation_id" not in ctx


# ---------------------------------------------------------------------------
# TestParseJsonParam
# ---------------------------------------------------------------------------

class TestParseJsonParam:
    def test_valid_json(self):
        result = chat_module._parse_json_param('{"key": "val"}', "search_params")
        assert result == {"key": "val"}

    def test_invalid_json_returns_none(self):
        result = chat_module._parse_json_param("not json", "search_params")
        assert result is None

    def test_none_input(self):
        result = chat_module._parse_json_param(None, "search_params")
        assert result is None

    def test_file_references_must_be_list(self):
        result = chat_module._parse_json_param('{"not": "a list"}', "file_references")
        assert result is None

    def test_file_references_list(self):
        result = chat_module._parse_json_param('["f1", "f2"]', "file_references")
        assert result == ["f1", "f2"]


# ---------------------------------------------------------------------------
# TestCallAgent
# ---------------------------------------------------------------------------

class TestCallAgent:
    @pytest.mark.asyncio
    async def test_happy_path(self, mocker):
        _patch_auth(mocker)
        _mock_process_files(mocker)
        svc = _mock_execution_service(mocker)

        result = await chat_module.call_agent(
            app_id=1,
            agent_id=1,
            message="Hello",
            files=[],
            file_references=None,
            search_params=None,
            conversation_id=None,
            api_key="key",
            db=MagicMock(),
        )
        assert result.response == "Hello!"
        assert result.conversation_id == 42

    @pytest.mark.asyncio
    async def test_agent_ownership_validated(self, mocker):
        mocker.patch.object(chat_module, "validate_api_key_for_app")
        mocker.patch.object(
            chat_module,
            "validate_agent_ownership",
            side_effect=HTTPException(status_code=404, detail="Agent not found"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await chat_module.call_agent(
                app_id=1, agent_id=999, message="hi", files=[],
                file_references=None, search_params=None,
                conversation_id=None, api_key="key", db=MagicMock(),
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_500_on_exception(self, mocker):
        _patch_auth(mocker)
        _mock_process_files(mocker)
        svc = _mock_execution_service(mocker)
        svc.execute_agent_chat_with_file_refs = AsyncMock(
            side_effect=RuntimeError("internal error details")
        )

        with pytest.raises(HTTPException) as exc_info:
            await chat_module.call_agent(
                app_id=1, agent_id=1, message="hi", files=[],
                file_references=None, search_params=None,
                conversation_id=None, api_key="key", db=MagicMock(),
            )
        assert exc_info.value.status_code == 500
        assert "internal error" not in exc_info.value.detail
        assert exc_info.value.detail == "Agent execution failed"


# ---------------------------------------------------------------------------
# TestCallAgentStream
# ---------------------------------------------------------------------------

class TestCallAgentStream:
    @pytest.mark.asyncio
    async def test_returns_streaming_response(self, mocker):
        _patch_auth(mocker)
        _mock_process_files(mocker)
        _mock_streaming_service(mocker)

        result = await chat_module.call_agent_stream(
            app_id=1, agent_id=1, message="Hello", files=[],
            file_references=None, search_params=None,
            conversation_id=None, api_key="key", db=MagicMock(),
        )
        assert isinstance(result, StreamingResponse)
        assert result.media_type == "text/event-stream"

    @pytest.mark.asyncio
    async def test_agent_ownership_validated(self, mocker):
        mocker.patch.object(chat_module, "validate_api_key_for_app")
        mocker.patch.object(
            chat_module,
            "validate_agent_ownership",
            side_effect=HTTPException(status_code=404, detail="Agent not found"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await chat_module.call_agent_stream(
                app_id=1, agent_id=999, message="hi", files=[],
                file_references=None, search_params=None,
                conversation_id=None, api_key="key", db=MagicMock(),
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# TestResetConversation
# ---------------------------------------------------------------------------

class TestResetConversation:
    @pytest.mark.asyncio
    async def test_happy_path(self, mocker):
        _patch_auth(mocker)
        svc = _mock_execution_service(mocker)

        result = await chat_module.reset_conversation(
            app_id=1, agent_id=1, conversation_id=None,
            api_key="key", db=MagicMock(),
        )
        assert result.message == "Conversation reset successfully"

    @pytest.mark.asyncio
    async def test_conversation_id_passed_in_context(self, mocker):
        _patch_auth(mocker)
        mock_ctx = mocker.patch.object(
            chat_module, "create_api_key_user_context",
            return_value={"user_id": "u", "app_id": 1, "oauth": False, "api_key": "k"},
        )
        svc = _mock_execution_service(mocker)

        await chat_module.reset_conversation(
            app_id=1, agent_id=1, conversation_id=42,
            api_key="key", db=MagicMock(),
        )

        # Verify the user_context passed to service contains conversation_id
        call_args = svc.reset_agent_conversation.call_args
        user_ctx = call_args.kwargs.get("user_context") or call_args[1].get("user_context")
        assert user_ctx["conversation_id"] == 42


# ---------------------------------------------------------------------------
# TestCreateConversation
# ---------------------------------------------------------------------------

class TestCreateConversation:
    @pytest.mark.asyncio
    async def test_happy_path(self, mocker):
        _patch_auth(mocker)
        conv = MagicMock()
        conv.conversation_id = 100
        conv.agent_id = 1
        conv.title = "Test"
        conv.created_at = None
        conv.updated_at = None

        mocker.patch.object(
            chat_module.ConversationService,
            "create_conversation",
            return_value=conv,
        )
        mocker.patch(
            "routers.public.v1.chat.PublicConversationSchema.model_validate",
            return_value=MagicMock(conversation_id=100),
        )

        body = MagicMock()
        body.title = "Test"

        result = await chat_module.create_conversation(
            app_id=1, agent_id=1, body=body, api_key="key", db=MagicMock(),
        )
        assert result.conversation_id == 100

    @pytest.mark.asyncio
    async def test_agent_ownership_validated(self, mocker):
        mocker.patch.object(chat_module, "validate_api_key_for_app")
        mocker.patch.object(
            chat_module,
            "validate_agent_ownership",
            side_effect=HTTPException(status_code=404, detail="Agent not found"),
        )

        body = MagicMock()
        body.title = None

        with pytest.raises(HTTPException) as exc_info:
            await chat_module.create_conversation(
                app_id=1, agent_id=999, body=body, api_key="key", db=MagicMock(),
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# TestListConversations
# ---------------------------------------------------------------------------

class TestListConversations:
    @pytest.mark.asyncio
    async def test_happy_path(self, mocker):
        _patch_auth(mocker)
        conv = MagicMock()
        conv.conversation_id = 1
        conv.agent_id = 1

        mocker.patch.object(
            chat_module.ConversationService,
            "list_conversations",
            return_value=([conv], 1),
        )
        mocker.patch(
            "routers.public.v1.chat.PublicConversationSchema.model_validate",
            return_value=MagicMock(conversation_id=1),
        )
        mock_list_response = mocker.patch(
            "routers.public.v1.chat.PublicConversationListResponseSchema"
        )
        mock_list_response.side_effect = lambda **kwargs: MagicMock(**kwargs)

        result = await chat_module.list_conversations(
            app_id=1, agent_id=1, limit=50, offset=0,
            api_key="key", db=MagicMock(),
        )
        assert result.total == 1
        assert len(result.conversations) == 1


# ---------------------------------------------------------------------------
# TestGetConversationWithHistory
# ---------------------------------------------------------------------------

class TestGetConversationWithHistory:
    @pytest.mark.asyncio
    async def test_happy_path(self, mocker):
        _patch_auth(mocker)
        conv = MagicMock()
        conv.conversation_id = 1
        conv.agent_id = 1
        conv.title = "Test"
        conv.created_at = None
        conv.updated_at = None

        mocker.patch.object(
            chat_module.ConversationService,
            "get_conversation",
            return_value=conv,
        )
        mocker.patch.object(
            chat_module.ConversationService,
            "get_conversation_history",
            new_callable=AsyncMock,
            return_value=[{"role": "user", "content": "hi"}],
        )

        result = await chat_module.get_conversation_with_history(
            app_id=1, agent_id=1, conversation_id=1,
            api_key="key", db=MagicMock(),
        )
        assert result.conversation_id == 1
        assert len(result.messages) == 1

    @pytest.mark.asyncio
    async def test_not_found(self, mocker):
        _patch_auth(mocker)
        mocker.patch.object(
            chat_module.ConversationService,
            "get_conversation",
            return_value=None,
        )

        with pytest.raises(HTTPException) as exc_info:
            await chat_module.get_conversation_with_history(
                app_id=1, agent_id=1, conversation_id=999,
                api_key="key", db=MagicMock(),
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# TestDeleteConversation
# ---------------------------------------------------------------------------

class TestDeleteConversation:
    @pytest.mark.asyncio
    async def test_happy_path(self, mocker):
        _patch_auth(mocker)
        mocker.patch.object(
            chat_module.ConversationService,
            "delete_conversation",
            new_callable=AsyncMock,
            return_value=True,
        )

        result = await chat_module.delete_conversation(
            app_id=1, agent_id=1, conversation_id=1,
            api_key="key", db=MagicMock(),
        )
        assert result.message == "Conversation deleted successfully"

    @pytest.mark.asyncio
    async def test_not_found(self, mocker):
        _patch_auth(mocker)
        mocker.patch.object(
            chat_module.ConversationService,
            "delete_conversation",
            new_callable=AsyncMock,
            return_value=False,
        )

        with pytest.raises(HTTPException) as exc_info:
            await chat_module.delete_conversation(
                app_id=1, agent_id=1, conversation_id=999,
                api_key="key", db=MagicMock(),
            )
        assert exc_info.value.status_code == 404
