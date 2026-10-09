"""
Integration tests for what happens to middlewares and their related entities on
deletion, rename and export/import:

  - deleting an agent with conversations (its conversations go with it)
  - deleting an app never leaves agents behind
  - an AI service used by a middleware cannot be deleted (409)
  - renaming an agent used as a tool keeps the approval rules that gate it
  - memory cannot be turned off under a human-approval middleware
  - middleware export/import on its own, with an agent and with the full app
"""

import json
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
def other_app(db, fake_user):
    from models.app import App

    app_obj = App(name="Other Workspace", slug="other-workspace-relations", owner_id=fake_user.user_id,
                  agent_rate_limit=0, max_file_size_mb=10)
    db.add(app_obj)
    db.flush()
    return app_obj


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


# ---------------------------------------------------------------------------
# Export / import
# ---------------------------------------------------------------------------

def _pii_with_detector(service: AIService) -> dict:
    return {"pii_types": ["email"], "llm_detector": {"enabled": True, "ai_service": f"ai_service:{service.service_id}"}}


class TestMiddlewareExportImport:
    def _export(self, client, app_id, middleware_id, headers) -> dict:
        response = client.post(f"{middlewares_url(app_id, middleware_id)}/export", headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    def _import(self, client, app_id, data, headers, conflict_mode="fail"):
        return client.post(
            f"/internal/apps/{app_id}/middlewares/import?conflict_mode={conflict_mode}",
            files={"file": ("mw.json", json.dumps(data), "application/json")},
            headers=headers,
        )

    def test_ai_service_travels_by_name(self, client, fake_app, other_app, fake_ai_service, owner_headers, db):
        same_name = AIService(name=fake_ai_service.name, provider="OpenAI", api_key="sk-test",  # pragma: allowlist secret
                              app_id=other_app.app_id)
        db.add(same_name)
        db.flush()
        mid = create_middleware(client, fake_app.app_id, owner_headers, "PII", "pii", _pii_with_detector(fake_ai_service))

        data = self._export(client, fake_app.app_id, mid, owner_headers)
        assert data["middleware"]["ai_service_name"] == fake_ai_service.name
        assert data["middleware"]["config"]["llm_detector"]["ai_service"] == "agent_llm"

        response = self._import(client, other_app.app_id, data, owner_headers)
        assert response.status_code == 201, response.text
        summary = response.json()["summary"]
        assert summary["warnings"] == []
        imported = client.get(middlewares_url(other_app.app_id, summary["component_id"]), headers=owner_headers)
        assert imported.json()["config"]["llm_detector"]["ai_service"] == f"ai_service:{same_name.service_id}"

    def test_missing_ai_service_falls_back_with_a_warning(
        self, client, fake_app, other_app, fake_ai_service, owner_headers, db
    ):
        db.flush()
        mid = create_middleware(client, fake_app.app_id, owner_headers, "PII", "pii", _pii_with_detector(fake_ai_service))
        data = self._export(client, fake_app.app_id, mid, owner_headers)

        response = self._import(client, other_app.app_id, data, owner_headers)

        assert response.status_code == 201, response.text
        assert "not found in this app" in response.json()["summary"]["warnings"][0]

    def test_conflict_modes(self, client, fake_app, owner_headers, db):
        db.flush()
        mid = create_middleware(client, fake_app.app_id, owner_headers, "Guard")
        data = self._export(client, fake_app.app_id, mid, owner_headers)

        assert self._import(client, fake_app.app_id, data, owner_headers).status_code == 409
        renamed = self._import(client, fake_app.app_id, data, owner_headers, "rename")
        assert renamed.status_code == 201
        assert renamed.json()["summary"]["component_name"].startswith("Guard (imported")

        data["middleware"]["middleware_type"] = "model_call_limit"
        data["middleware"]["config"] = {"max_calls": 5}
        assert self._import(client, fake_app.app_id, data, owner_headers, "override").status_code == 409

    def test_invalid_file_is_rejected(self, client, fake_app, owner_headers, db):
        db.flush()
        response = self._import(client, fake_app.app_id, {"not": "a middleware"}, owner_headers)
        assert response.status_code == 400


class TestAgentAndAppExportImport:
    def test_agent_keeps_its_middlewares(self, client, fake_app, other_app, fake_ai_service, owner_headers, db):
        from schemas.import_schemas import ConflictMode
        from services.agent_export_service import AgentExportService
        from services.agent_import_service import AgentImportService

        db.flush()
        guard = create_middleware(client, fake_app.app_id, owner_headers, "Guard")
        limit = create_middleware(client, fake_app.app_id, owner_headers, "Limit", "model_call_limit", {"max_calls": 5})
        agent = create_agent(client, fake_app.app_id, owner_headers, fake_ai_service.service_id, [limit, guard])
        target_service = AIService(name="Target", provider="OpenAI", api_key="sk-test",  # pragma: allowlist secret
                                   app_id=other_app.app_id)
        db.add(target_service)
        db.flush()

        export_file = AgentExportService(db).export_agent(agent["agent_id"], fake_app.app_id)
        assert export_file.agent.middleware_names == ["Limit", "Guard"]
        summary = AgentImportService(db).import_agent(
            export_file, other_app.app_id, ConflictMode.RENAME, selected_ai_service_id=target_service.service_id
        )

        imported = client.get(agents_url(other_app.app_id, summary.component_id), headers=owner_headers).json()
        names = {m.middleware_id: m.name for m in db.query(Middleware).filter(Middleware.app_id == other_app.app_id)}
        assert [names[i] for i in imported["middleware_ids"]] == ["Limit", "Guard"]

    def test_full_app_round_trip(self, client, fake_app, fake_user, fake_ai_service, owner_headers, db):
        from services.full_app_export_service import FullAppExportService
        from services.full_app_import_service import FullAppImportService

        fake_ai_service.description = "gpt-4o-mini"  # exported as the model name
        db.flush()
        pii = create_middleware(client, fake_app.app_id, owner_headers, "PII", "pii", _pii_with_detector(fake_ai_service))
        create_agent(client, fake_app.app_id, owner_headers, fake_ai_service.service_id, [pii], name="Main")

        export_file = FullAppExportService(db).export_full_app(fake_app.app_id, fake_user.user_id)
        assert [m.name for m in export_file.middlewares] == ["PII"]
        summary = FullAppImportService(db).import_full_app(export_file, fake_user.user_id, new_name="Copy")

        assert summary.components_imported["middlewares"] == 1
        new_app_id = summary.app_id
        imported_pii = db.query(Middleware).filter(Middleware.app_id == new_app_id).one()
        new_service = db.query(AIService).filter(AIService.app_id == new_app_id).one()
        assert imported_pii.config["llm_detector"]["ai_service"] == f"ai_service:{new_service.service_id}"
        new_agent = db.query(Agent).filter(Agent.app_id == new_app_id, Agent.name == "Main").one()
        assert [a.middleware_id for a in new_agent.middleware_associations] == [imported_pii.middleware_id]

    def test_full_app_import_keeps_tool_agents(self, client, fake_app, fake_user, fake_ai_service, owner_headers, db):
        """An agent sorted before its tool agent still gets it, and the tool keeps is_tool."""
        from models.agent import AgentTool
        from services.full_app_export_service import FullAppExportService
        from services.full_app_import_service import FullAppImportService

        fake_ai_service.description = "gpt-4o-mini"
        db.flush()
        tool = create_agent(client, fake_app.app_id, owner_headers, fake_ai_service.service_id, [],
                            name="Zeta tool", is_tool=True)
        create_agent(client, fake_app.app_id, owner_headers, fake_ai_service.service_id, [],
                     name="Alpha main", tool_ids=[tool["agent_id"]])

        export_file = FullAppExportService(db).export_full_app(fake_app.app_id, fake_user.user_id)
        summary = FullAppImportService(db).import_full_app(export_file, fake_user.user_id, new_name="Copy")

        agents = {a.name: a for a in db.query(Agent).filter(Agent.app_id == summary.app_id)}
        assert agents["Zeta tool"].is_tool is True
        tool_ids = [t.tool_id for t in db.query(AgentTool).filter(AgentTool.agent_id == agents["Alpha main"].agent_id)]
        assert tool_ids == [agents["Zeta tool"].agent_id]
