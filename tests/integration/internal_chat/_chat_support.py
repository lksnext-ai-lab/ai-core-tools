"""Shared fakes, world fixture and HTTP helpers of the Chat integration tests (lifted from test_chat_functional).

Originally documented in the functional tests (app-flexible-chat step_009):

Everything runs for real (router, ``InternalChatService``, resolver, execution/streaming services, LangGraph
checkpointer, PostgreSQL) except four fakes:

* the LLM: ``tools.aiServiceTools.create_llm_from_service`` returns a recording fake per ``ai_service_id``;
* the retriever tool: ``tools.agentTools.get_retriever_tool`` returns a tool tagged with the silo id;
* the MCP client: ``tools.agentTools.MultiServerMCPClient`` exposes one tool per configured server name;
* the metrics write: ``services.agent_metrics_recorder.persist_metrics_payload`` captures the payload (the real one
  writes on its own session, which cannot see the test transaction).

The stream closes the shared request session (``db.close()`` in the router), so the fixtures keep plain ids only.
Checkpoints are written by the real checkpointer on its own connections: ``fakes`` removes them after each test.
"""
import json
import threading
from typing import Any, Optional

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import StructuredTool
from sqlalchemy import text

from models.agent import Agent
from models.agent_execution_event import AgentExecutionEvent
from models.conversation import Conversation
from models.internal_chat import ConversationTurn
from models.mcp_config import MCPConfig
from models.silo import Silo
from models.skill import Skill
from tests.factories import (
    AIServiceFactory,
    AppFactory,
    EmbeddingServiceFactory,
    UserFactory,
    configure_factories,
)
from tests.integration.routers.internal._eos_helpers import headers_for, member_headers
from models.app_collaborator import CollaborationRole

NOT_FOUND = {"detail": "Resource not found", "error_code": "NOT_FOUND"}


# ------------------------------------------------------------------ fakes


class Recorder:
    """What the fakes saw. Appended from the app's event-loop thread, read from the test thread."""

    def __init__(self):
        self.calls: list[tuple[int, list[tuple[str, str]]]] = []  # (service_id, [(message type, text)])
        self.bound_tools: dict[int, list[list[str]]] = {}  # service_id -> tool names per model call
        self.fail_services: set[int] = set()
        self.mcp_clients: list[dict] = []  # connections each fake MCP client was built with
        self.payloads: list[dict] = []  # metrics payloads
        self._cond = threading.Condition()

    def calls_of(self, service_id: int):
        return [messages for sid, messages in self.calls if sid == service_id]

    def system_prompt(self, service_id: int, index: int = -1) -> str:
        return next(content for kind, content in self.calls_of(service_id)[index] if kind == "system")

    def tools_of(self, service_id: int, index: int = -1) -> list[str]:
        return self.bound_tools[service_id][index]

    def add_payload(self, payload: dict) -> None:
        with self._cond:
            self.payloads.append(payload)
            self._cond.notify_all()

    def wait_payloads(self, count: int, timeout: float = 15.0) -> list[dict]:
        with self._cond:
            assert self._cond.wait_for(lambda: len(self.payloads) >= count, timeout), (
                f"expected {count} metrics payload(s), got {len(self.payloads)}"
            )
            return list(self.payloads)


class FakeChatModel(BaseChatModel):
    """Chat model that records what it receives and answers ``hello from <service_id>``."""

    service_id: int
    rec: Any

    @property
    def _llm_type(self) -> str:
        return "recording-fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.rec.calls.append((self.service_id, [(m.type, m.text) for m in messages]))
        if self.service_id in self.rec.fail_services:
            raise RuntimeError("fake llm failure")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=f"hello from {self.service_id}"))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        # Streaming path: the same answer, split in words, so the real stack emits several token events.
        self.rec.calls.append((self.service_id, [(m.type, m.text) for m in messages]))
        if self.service_id in self.rec.fail_services:
            raise RuntimeError("fake llm failure")
        words = f"hello from {self.service_id}".split(" ")
        for index, word in enumerate(words):
            chunk = AIMessageChunk(content=word if index == 0 else f" {word}")
            if run_manager:
                run_manager.on_llm_new_token(chunk.text, chunk=ChatGenerationChunk(message=chunk))
            yield ChatGenerationChunk(message=chunk)

    def bind_tools(self, tools, **kwargs):
        names = [getattr(t, "name", None) or t.get("name") or t["function"]["name"] for t in tools]
        self.rec.bound_tools.setdefault(self.service_id, []).append(names)
        return self


def _tool(name: str) -> StructuredTool:
    def run(query: str = "") -> str:
        return "nothing"

    return StructuredTool.from_function(func=run, name=name, description=f"fake tool {name}")


class FakeMCPClient:
    """Exposes one tool per server name of the config; a server named ``boom*`` fails on connect."""

    rec: Recorder

    def __init__(self, connections=None, **_):
        self.connections = connections or {}
        self.rec.mcp_clients.append(dict(self.connections))

    async def get_tools(self):
        if any(name.startswith("boom") for name in self.connections):
            raise ConnectionError("cannot connect to the MCP server")
        return [_tool(f"mcp_{name}") for name in self.connections]


@pytest.fixture
def fakes(db, test_engine, monkeypatch):
    rec = Recorder()

    def fake_llm(ai_service, temperature=0, is_vision=False):
        return FakeChatModel(service_id=ai_service.service_id, rec=rec)

    def fake_retriever(silo, *args, **kwargs):
        return _tool(f"retriever_silo_{silo.silo_id}")

    async def capture_metrics(payload):
        rec.add_payload(payload)

    mcp_cls = type("BoundFakeMCPClient", (FakeMCPClient,), {"rec": rec})
    monkeypatch.setattr("tools.aiServiceTools.create_llm_from_service", fake_llm)
    monkeypatch.setattr("tools.agentTools.get_retriever_tool", fake_retriever)
    monkeypatch.setattr("tools.agentTools.MultiServerMCPClient", mcp_cls)
    monkeypatch.setattr("services.agent_metrics_recorder.persist_metrics_payload", capture_metrics)
    yield rec

    # The checkpointer wrote on its own connections: remove the threads of this test's conversations.
    db.rollback()
    threads = [
        f"thread_{agent_id}_{session_id}"
        for agent_id, session_id in db.query(Conversation.agent_id, Conversation.session_id)
        .join(Agent, Agent.agent_id == Conversation.agent_id)
        .filter(Agent.kind == "internal_chat")
        .all()
    ]
    if threads:
        # One autocommit statement per table, in the checkpointer's own order (``adelete_thread``): no transaction
        # holds locks on one table while waiting for another, so a background thread delete cannot deadlock with it.
        with test_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
                conn.execute(text(f"DELETE FROM {table} WHERE thread_id = ANY(:ids)"), {"ids": threads})


# ------------------------------------------------------------------ world


@pytest.fixture
def world(db):
    """App A (alice owns it) with two AI services and an embedding service; App B (bob) with one of everything.

    Committed into the test transaction and reduced to plain ids: a streamed turn closes the shared session.
    """
    configure_factories(db)
    alice, bob = UserFactory(), UserFactory()
    app, other_app = AppFactory(owner=alice), AppFactory(owner=bob)
    ai_a = AIServiceFactory(app=app, name="model-a", description="gpt-a")
    ai_b = AIServiceFactory(app=app, name="model-b", description="gpt-b")
    other_ai = AIServiceFactory(app=other_app, name="foreign-model", description="gpt-z")
    emb = EmbeddingServiceFactory(app=app)
    other_emb = EmbeddingServiceFactory(app=other_app)
    db.flush()
    other_silo = Silo(name="foreign-silo", app_id=other_app.app_id, embedding_service_id=other_emb.service_id)
    other_skill = Skill(name="foreign-skill", content="x", app_id=other_app.app_id)
    other_mcp = MCPConfig(
        name="foreign-mcp", config={"foreign": {"url": "http://x", "transport": "streamable_http"}},
        app_id=other_app.app_id,
    )
    db.add_all([other_silo, other_skill, other_mcp])
    db.flush()
    world = {
        "app_id": app.app_id, "other_app_id": other_app.app_id,
        "alice_id": alice.user_id, "bob_id": bob.user_id,
        "alice": headers_for(alice), "bob": headers_for(bob),
        "viewer": member_headers(db, app, CollaborationRole.VIEWER),
        "ai_a": ai_a.service_id, "ai_b": ai_b.service_id, "emb": emb.service_id,
        "other_ai": other_ai.service_id, "other_silo": other_silo.silo_id,
        "other_skill": other_skill.skill_id, "other_mcp": other_mcp.config_id,
    }
    db.commit()
    return world


def base(app_id: int) -> str:
    return f"/internal/apps/{app_id}/chat"


def selection(ai: int, silo: Optional[int] = None, skills=(), mcps=()) -> dict:
    return {"ai_service_id": ai, "silo_id": silo, "skill_ids": list(skills), "mcp_config_ids": list(mcps)}


def turn_form(message: str, sel: dict, conversation_id: Optional[int] = None) -> dict:
    data = {"message": message, "selection": json.dumps(sel)}
    if conversation_id is not None:
        data["conversation_id"] = str(conversation_id)
    return data


def send(client, world, message, sel, conversation_id=None, who="alice", app_key="app_id", path="/messages"):
    return client.post(
        base(world[app_key]) + path, headers=world[who], data=turn_form(message, sel, conversation_id)
    )


def ok_turn(client, world, message, sel, conversation_id=None, who="alice") -> dict:
    response = send(client, world, message, sel, conversation_id, who)
    assert response.status_code == 200, response.text
    return response.json()


def parse_sse(body: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in body.splitlines() if line.startswith("data: ")]


def sse_turn(client, world, message, sel, conversation_id=None, who="alice") -> list[dict]:
    response = send(client, world, message, sel, conversation_id, who, path="/stream")
    assert response.status_code == 200, response.text
    return parse_sse(response.text)


def detail(client, world, cid, who="alice") -> dict:
    response = client.get(f"{base(world['app_id'])}/conversations/{cid}", headers=world[who])
    assert response.status_code == 200, response.text
    return response.json()


def internal_conversations(db, app_id) -> int:
    return (
        db.query(Conversation).join(Agent, Agent.agent_id == Conversation.agent_id)
        .filter(Agent.app_id == app_id, Agent.kind == "internal_chat").count()
    )


def turns_in(db, app_id) -> int:
    return db.query(ConversationTurn).filter(ConversationTurn.app_id == app_id).count()


def events_in(db, app_id) -> int:
    return db.query(AgentExecutionEvent).filter(AgentExecutionEvent.app_id == app_id).count()


def message_total(db, app_id) -> int:
    return sum(
        c.message_count
        for c in db.query(Conversation).join(Agent, Agent.agent_id == Conversation.agent_id)
        .filter(Agent.app_id == app_id).all()
    )
