"""
Integration tests for the conversations endpoints.

Endpoints under test (backend/routers/internal/conversations.py):
  - POST   /internal/conversations                            (create conversation)
  - GET    /internal/conversations?agent_id=...                (list conversations)
  - GET    /internal/conversations/{conversation_id}           (get conversation)
  - GET    /internal/conversations/{conversation_id}/history   (get conversation + message history)
  - PATCH  /internal/conversations/{conversation_id}           (update conversation)

Regression coverage:
  `ConversationResponse` (backend/schemas/conversation_schemas.py) used to declare
  a required `app_id: int` field that nothing ever populated -- no column on the
  `Conversation` ORM model, no service logic setting it. Every endpoint here that
  serializes a raw `Conversation` ORM object through `ConversationResponse` (or
  `ConversationWithHistoryResponse`, which inherits from it) raised a Pydantic
  `ResponseValidationError` ("Field required [type=missing] ... app_id"), i.e. a
  500 on every call. This suite exercises the full router with zero mocking of
  the response schema to catch any regression of that bug.
"""

import pytest


# ---------------------------------------------------------------------------
# Create conversation
# ---------------------------------------------------------------------------


class TestCreateConversation:
    """POST /internal/conversations"""

    def test_create_conversation_returns_200_with_expected_fields(
        self, client, fake_agent, auth_headers, db
    ):
        db.flush()
        response = client.post(
            f"/internal/conversations?agent_id={fake_agent.agent_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["conversation_id"], int)
        assert body["agent_id"] == fake_agent.agent_id
        assert body["session_id"].startswith(f"conv_{fake_agent.agent_id}_")
        assert body["message_count"] == 0
        assert body["last_message"] is None
        assert "created_at" in body
        assert "updated_at" in body
        # The bug reported app_id as a required-but-unpopulated field on this
        # schema; it must not be present anymore (it was removed entirely).
        assert "app_id" not in body

    def test_create_conversation_with_title(self, client, fake_agent, auth_headers, db):
        db.flush()
        response = client.post(
            "/internal/conversations",
            headers=auth_headers,
            params={"agent_id": fake_agent.agent_id, "title": "My Chat"},
        )

        assert response.status_code == 200
        assert response.json()["title"] == "My Chat"

    def test_create_conversation_without_title_gets_auto_title(
        self, client, fake_agent, auth_headers, db
    ):
        db.flush()
        response = client.post(
            f"/internal/conversations?agent_id={fake_agent.agent_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["title"]  # auto-generated, non-empty


# ---------------------------------------------------------------------------
# List conversations
# ---------------------------------------------------------------------------


class TestListConversations:
    """GET /internal/conversations?agent_id=..."""

    def test_list_conversations_after_create(self, client, fake_agent, auth_headers, db):
        """
        Regression test for the app_id ResponseValidationError bug.

        Prior to the fix, `ConversationResponse` required an `app_id: int`
        field that nothing populated, so this endpoint raised a 500
        ResponseValidationError (`Field required [type=missing] ... app_id`)
        for any Conversation ORM object serialized through it -- meaning
        listing conversations was completely broken.
        """
        db.flush()
        create_resp = client.post(
            f"/internal/conversations?agent_id={fake_agent.agent_id}",
            headers=auth_headers,
        )
        assert create_resp.status_code == 200
        created_id = create_resp.json()["conversation_id"]

        list_resp = client.get(
            "/internal/conversations",
            headers=auth_headers,
            params={"agent_id": fake_agent.agent_id},
        )

        assert list_resp.status_code == 200
        body = list_resp.json()
        assert body["total"] == 1
        assert len(body["conversations"]) == 1
        assert body["conversations"][0]["conversation_id"] == created_id
        assert "app_id" not in body["conversations"][0]

    def test_list_conversations_empty_for_agent_with_none(
        self, client, fake_agent, auth_headers, db
    ):
        db.flush()
        response = client.get(
            "/internal/conversations",
            headers=auth_headers,
            params={"agent_id": fake_agent.agent_id},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 0
        assert body["conversations"] == []


# ---------------------------------------------------------------------------
# Get conversation
# ---------------------------------------------------------------------------


class TestGetConversation:
    """GET /internal/conversations/{conversation_id}"""

    def test_get_conversation_by_id(self, client, fake_agent, auth_headers, db):
        db.flush()
        created = client.post(
            f"/internal/conversations?agent_id={fake_agent.agent_id}",
            headers=auth_headers,
        ).json()

        response = client.get(
            f"/internal/conversations/{created['conversation_id']}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["conversation_id"] == created["conversation_id"]
        assert body["agent_id"] == fake_agent.agent_id

    def test_get_conversation_not_found_returns_404(self, client, auth_headers, db):
        response = client.get(
            "/internal/conversations/999999",
            headers=auth_headers,
        )

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Get conversation history
# ---------------------------------------------------------------------------


class TestGetConversationHistory:
    """GET /internal/conversations/{conversation_id}/history"""

    def test_history_is_empty_for_fresh_conversation(
        self, client, fake_agent, auth_headers, db
    ):
        """A freshly created conversation has no LangGraph checkpointer
        messages yet, so `messages` must come back as an empty list."""
        db.flush()
        created = client.post(
            f"/internal/conversations?agent_id={fake_agent.agent_id}",
            headers=auth_headers,
        ).json()

        response = client.get(
            f"/internal/conversations/{created['conversation_id']}/history",
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["conversation_id"] == created["conversation_id"]
        assert body["messages"] == []
        assert "app_id" not in body

    def test_history_not_found_returns_404(self, client, auth_headers, db):
        response = client.get(
            "/internal/conversations/999999/history",
            headers=auth_headers,
        )

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update conversation
# ---------------------------------------------------------------------------


class TestUpdateConversation:
    """PATCH /internal/conversations/{conversation_id}"""

    def test_update_title(self, client, fake_agent, auth_headers, db):
        db.flush()
        created = client.post(
            f"/internal/conversations?agent_id={fake_agent.agent_id}",
            headers=auth_headers,
        ).json()

        response = client.patch(
            f"/internal/conversations/{created['conversation_id']}",
            headers=auth_headers,
            json={"title": "New Title"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "New Title"
        assert body["conversation_id"] == created["conversation_id"]

    def test_update_not_found_returns_404(self, client, auth_headers, db):
        response = client.patch(
            "/internal/conversations/999999",
            headers=auth_headers,
            json={"title": "New Title"},
        )

        assert response.status_code == 404
