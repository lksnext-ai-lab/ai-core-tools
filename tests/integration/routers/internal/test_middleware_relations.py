"""
Integration tests for what happens to middlewares and their related entities on
deletion and rename:

  - deleting an agent with conversations (its conversations go with it)
  - deleting an app never leaves agents behind
  - an AI service used by a middleware cannot be deleted (409)
  - renaming an agent used as a tool keeps the approval rules that gate it
  - memory cannot be turned off under a human-approval middleware
"""

import uuid

import pytest

from models.agent import Agent
from models.ai_service import AIService
from models.conversation import Conversation
from models.middleware import Middleware

pytestmark = pytest.mark.integration


def middlewares_url(app_id: int, middleware_id) -> str:
    return f"/internal/apps/{app_id}/middlewares/{middleware_id}"


def agents_url(app_id: int, agent_id) -> str:
    return f"/internal/apps/{app_id}/agents/{agent_id}"


def create_middleware(client, app_id, headers, name, middleware_type="guardrails", config=None) -> int:
    response = client.post(
        middlewares_url(app_id, 0),
        json={"name": name, "description": "", "middleware_type": middleware_type, "config": config},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["middleware_id"]


def create_agent(client, app_id, headers, service_id, middleware_ids, name="Agent", has_memory=False, **extra) -> dict:
    payload = {"name": name, "service_id": service_id, "has_memory": has_memory,
               "middleware_ids": middleware_ids, **extra}
    response = client.post(agents_url(app_id, 0), json=payload, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()


def approval_rules(tool_name: str) -> dict:
    return {"interrupt_on": {tool_name: {"allowed_decisions": ["approve", "reject"]}}}


@pytest.fixture
def deleted_threads(monkeypatch):
    """Record checkpoint deletions instead of reaching the LangGraph checkpointer."""
    from services.conversation_service import ConversationService

    recorded = []
    monkeypatch.setattr(ConversationService, "delete_thread_histories_in_background",
                        staticmethod(lambda threads: recorded.extend(threads)))
    return recorded


def add_conversation(db, agent_id: int) -> Conversation:
    conversation = Conversation(agent_id=agent_id, session_id=f"conv_{agent_id}_{uuid.uuid4()}", title="Chat")
    db.add(conversation)
    db.flush()
    return conversation


# ---------------------------------------------------------------------------
# Agent and app deletion
# ---------------------------------------------------------------------------

class TestAgentAndAppDeletion:
    def test_agent_with_conversations_is_deleted_with_them(
        self, client, fake_app, fake_ai_service, owner_headers, db, deleted_threads
    ):
        db.flush()
        mid = create_middleware(client, fake_app.app_id, owner_headers, "Guard")
        agent = create_agent(client, fake_app.app_id, owner_headers, fake_ai_service.service_id, [mid])
        conversation = add_conversation(db, agent["agent_id"])
        conversation_id, session_id = conversation.conversation_id, conversation.session_id

        response = client.delete(agents_url(fake_app.app_id, agent["agent_id"]), headers=owner_headers)

        assert response.status_code == 200, response.text
        db.expire_all()
        assert db.get(Agent, agent["agent_id"]) is None
        assert db.get(Conversation, conversation_id) is None
        assert db.get(Middleware, mid) is not None
        assert deleted_threads == [(agent["agent_id"], session_id)]

    def test_app_deletion_leaves_no_agent_behind(
        self, client, fake_app, fake_ai_service, owner_headers, db, deleted_threads
    ):
        db.flush()
        mid = create_middleware(client, fake_app.app_id, owner_headers, "Detector", "pii", {
            "pii_types": ["email"],
            "llm_detector": {"enabled": True, "ai_service": f"ai_service:{fake_ai_service.service_id}"},
        })
        agent = create_agent(client, fake_app.app_id, owner_headers, fake_ai_service.service_id, [mid])
        add_conversation(db, agent["agent_id"])

        response = client.delete(f"/internal/apps/{fake_app.app_id}", headers=owner_headers)

        assert response.status_code == 200, response.text
        db.expire_all()
        assert db.get(Agent, agent["agent_id"]) is None
        assert db.query(Agent).filter(Agent.app_id.is_(None)).count() == 0
        assert db.get(Middleware, mid) is None


# ---------------------------------------------------------------------------
# AI services referenced by middlewares
# ---------------------------------------------------------------------------

class TestAIServiceInUse:
    def test_ai_service_used_by_a_middleware_cannot_be_deleted(
        self, client, fake_app, fake_ai_service, owner_headers, db
    ):
        db.flush()
        detector = AIService(name="Local detector", provider="OpenAI", api_key="sk-test",  # pragma: allowlist secret
                             app_id=fake_app.app_id)
        db.add(detector)
        db.flush()
        config = {"pii_types": ["email"],
                  "llm_detector": {"enabled": True, "ai_service": f"ai_service:{detector.service_id}"}}
        mid = create_middleware(client, fake_app.app_id, owner_headers, "PII detector", "pii", config)
        url = f"/internal/apps/{fake_app.app_id}/ai-services/{detector.service_id}"

        response = client.delete(url, headers=owner_headers)

        assert response.status_code == 409
        assert "'PII detector'" in response.json()["detail"]
        assert db.get(AIService, detector.service_id) is not None

        config["llm_detector"]["ai_service"] = "agent_llm"
        client.post(middlewares_url(fake_app.app_id, mid), headers=owner_headers, json={
            "name": "PII detector", "description": "", "middleware_type": "pii", "config": config,
        })
        assert client.delete(url, headers=owner_headers).status_code == 200


# ---------------------------------------------------------------------------
# Agents used as tools
# ---------------------------------------------------------------------------

class TestToolAgentRename:
    def test_rename_moves_the_approval_rule(self, client, fake_app, fake_ai_service, owner_headers, db):
        db.flush()
        tool = create_agent(client, fake_app.app_id, owner_headers, fake_ai_service.service_id, [],
                            name="Docs Search", is_tool=True)
        hitl = create_middleware(client, fake_app.app_id, owner_headers, "Approve docs",
                                 "human_in_the_loop", approval_rules("Docs_Search"))
        create_agent(client, fake_app.app_id, owner_headers, fake_ai_service.service_id, [hitl],
                     name="Main", has_memory=True, tool_ids=[tool["agent_id"]])

        response = client.post(agents_url(fake_app.app_id, tool["agent_id"]), headers=owner_headers, json={
            "name": "Docs Finder", "service_id": fake_ai_service.service_id, "is_tool": True,
        })

        assert response.status_code in (200, 201), response.text
        rules = client.get(middlewares_url(fake_app.app_id, hitl), headers=owner_headers).json()["config"]
        assert list(rules["interrupt_on"]) == ["Docs_Finder"]


class TestMemoryWithApproval:
    def test_memory_cannot_be_turned_off_without_sending_the_chain(
        self, client, fake_app, fake_ai_service, owner_headers, db
    ):
        db.flush()
        hitl = create_middleware(client, fake_app.app_id, owner_headers, "Approve",
                                 "human_in_the_loop", approval_rules("search"))
        agent = create_agent(client, fake_app.app_id, owner_headers, fake_ai_service.service_id, [hitl],
                             has_memory=True)

        response = client.post(agents_url(fake_app.app_id, agent["agent_id"]), headers=owner_headers, json={
            "name": "Agent", "service_id": fake_ai_service.service_id, "has_memory": False,
        })

        assert response.status_code == 400
        assert "memory" in response.json()["detail"]
