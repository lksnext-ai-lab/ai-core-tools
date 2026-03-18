"""
Integration tests for public API chat endpoints.

LLM execution and file storage are mocked — these tests validate
the HTTP layer: routing, status codes, auth, and Pydantic serialization.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def chat_url(app_id: int, agent_id: int, path: str = "") -> str:
    return f"/public/v1/app/{app_id}/chat/{agent_id}{path}"


def api_headers(key: str) -> dict:
    return {"X-API-KEY": key}


MOCK_CHAT_RESULT = {
    "response": "Hello from integration test!",
    "conversation_id": 1,
    "metadata": {"agent_name": "Test", "agent_type": "agent",
                  "files_processed": 0, "has_memory": False},
}


# ---------------------------------------------------------------------------
# Call agent
# ---------------------------------------------------------------------------


class TestCallAgent:
    def test_call_agent_returns_200(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        with patch(
            "services.agent_execution_service.AgentExecutionService"
            ".execute_agent_chat_with_file_refs",
            new=AsyncMock(return_value=MOCK_CHAT_RESULT),
        ), patch(
            "routers.public.v1.chat._process_chat_files",
            new=AsyncMock(return_value=[]),
        ):
            resp = client.post(
                chat_url(fake_app.app_id, fake_agent.agent_id, "/call"),
                data={"message": "Hello"},
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Hello from integration test!"
        assert data["conversation_id"] == 1
        assert "usage" in data

    def test_agent_wrong_app_returns_404(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        other_app_id = fake_app.app_id + 1000
        resp = client.post(
            chat_url(other_app_id, fake_agent.agent_id, "/call"),
            data={"message": "Hello"},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code in (401, 403, 404)


# ---------------------------------------------------------------------------
# Call agent (streaming)
# ---------------------------------------------------------------------------


class TestCallAgentStream:
    def test_stream_returns_event_stream(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        async def mock_generator():
            yield 'data: {"type": "token", "data": "hi"}\n\n'

        with patch(
            "routers.public.v1.chat._process_chat_files",
            new=AsyncMock(return_value=[]),
        ), patch(
            "services.agent_streaming_service.AgentStreamingService"
            ".stream_agent_chat",
            return_value=mock_generator(),
        ):
            resp = client.post(
                chat_url(fake_app.app_id, fake_agent.agent_id, "/call/stream"),
                data={"message": "Hello"},
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Reset conversation
# ---------------------------------------------------------------------------


class TestResetConversation:
    def test_reset_returns_200(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        with patch(
            "services.agent_execution_service.AgentExecutionService"
            ".reset_agent_conversation",
            new=AsyncMock(return_value=True),
        ):
            resp = client.post(
                chat_url(fake_app.app_id, fake_agent.agent_id, "/reset"),
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 200
        assert resp.json()["message"] == "Conversation reset successfully"


# ---------------------------------------------------------------------------
# Create conversation
# ---------------------------------------------------------------------------


class TestCreateConversation:
    def test_create_returns_201(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        with patch(
            "services.conversation_service.ConversationService"
            ".create_conversation",
        ) as mock_create:
            conv = MagicMock()
            conv.conversation_id = 42
            conv.agent_id = fake_agent.agent_id
            conv.title = "Test Conversation"
            conv.created_at = None
            conv.updated_at = None
            mock_create.return_value = conv

            resp = client.post(
                chat_url(fake_app.app_id, fake_agent.agent_id, "/conversations"),
                json={"title": "Test Conversation"},
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["conversation_id"] == 42
        assert data["title"] == "Test Conversation"


# ---------------------------------------------------------------------------
# List conversations
# ---------------------------------------------------------------------------


class TestListConversations:
    def test_list_returns_200(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        with patch(
            "services.conversation_service.ConversationService"
            ".list_conversations",
        ) as mock_list:
            conv = MagicMock()
            conv.conversation_id = 1
            conv.agent_id = fake_agent.agent_id
            conv.title = "Conv 1"
            conv.created_at = None
            conv.updated_at = None
            mock_list.return_value = ([conv], 1)

            resp = client.get(
                chat_url(fake_app.app_id, fake_agent.agent_id, "/conversations"),
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["conversations"]) == 1


# ---------------------------------------------------------------------------
# Get conversation with history
# ---------------------------------------------------------------------------


class TestGetConversationWithHistory:
    def test_not_found_returns_404(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        with patch(
            "services.conversation_service.ConversationService"
            ".get_conversation",
            return_value=None,
        ):
            resp = client.get(
                chat_url(fake_app.app_id, fake_agent.agent_id, "/conversations/999"),
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete conversation
# ---------------------------------------------------------------------------


class TestDeleteConversation:
    def test_not_found_returns_404(
        self, client, fake_app, fake_agent, fake_api_key, db
    ):
        with patch(
            "services.conversation_service.ConversationService"
            ".delete_conversation",
            new=AsyncMock(return_value=False),
        ):
            resp = client.delete(
                chat_url(fake_app.app_id, fake_agent.agent_id, "/conversations/999"),
                headers=api_headers(fake_api_key.key),
            )

        assert resp.status_code == 404
