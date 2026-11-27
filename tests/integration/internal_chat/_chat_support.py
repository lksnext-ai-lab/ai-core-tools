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
import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Optional

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import StructuredTool
from sqlalchemy import select, text, tuple_
from sqlalchemy.orm import Session

from db.database import Base
from models.agent import Agent
from models.ai_service import AIService
from models.app import App
from models.agent_execution_event import AgentExecutionEvent
from models.conversation import Conversation
from models.internal_chat import ConversationTurn
from models.mcp_config import MCPConfig
from models.silo import Silo
from models.skill import Skill
from models.user import User
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


@pytest.fixture
def worker_session_on_test_db(db, monkeypatch):
    """Let the Chat's indexing worker thread (which opens its own session) see the test's uncommitted data.

    In production the worker opens a session of its own; here every session lives in the ``db`` fixture's
    transaction, so the worker gets a session on the SAME connection (the awaiting request does not use it meanwhile).
    """
    from contextlib import contextmanager

    from sqlalchemy.orm import Session

    @contextmanager
    def opener():
        session = Session(bind=db.get_bind(), join_transaction_mode="create_savepoint", autoflush=False)
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr("services.chat_attachment_service.open_indexing_session", opener)


# ------------------------------------------------------------------ LangGraph thread probe and log capture (shared)

CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


class ThreadProbe:
    """Row counts of LangGraph threads, relative to what the DB held when the test started.

    The LangGraph tables are not in ``Base.metadata``: they survive ``drop_all`` and agent ids restart at 1, so the
    DB can hold ``thread_1_conv_1_<uuid>`` rows, or fixed-name leftovers (``thread_1``, ``thread_1_default``), of
    earlier runs. A thread counts as "this test's" when it is new or its total row count changed, so a turn that also
    wrote into a leftover thread is still seen.
    """

    def __init__(self, engine):
        self.engine = engine
        self.baseline = self.counts()

    def counts(self) -> dict[str, int]:
        found: dict[str, int] = {}
        with self.engine.connect() as conn:
            for table in CHECKPOINT_TABLES:
                for thread_id, n in conn.execute(text(f"SELECT thread_id, count(*) FROM {table} GROUP BY thread_id")):
                    found[thread_id] = found.get(thread_id, 0) + n
        return found

    def rows(self, thread_id: str) -> int:
        """Rows of one thread over the three checkpoint tables (all must be gone after a delete or reset)."""
        return self.counts().get(thread_id, 0)

    def of_agent(self, agent_id: int) -> set[str]:
        """Threads of ``agent_id`` written by this test: ``thread_<id>`` and ``thread_<id>_*`` (not agents 10-19)."""
        prefix = f"thread_{agent_id}_"
        return {
            t for t, n in self.counts().items()
            if (t == f"thread_{agent_id}" or t.startswith(prefix)) and self.baseline.get(t) != n
        }

    def assert_agent_wide_thread_untouched(self, agent_id: int) -> None:
        """No row was added to the agent-wide thread (the one a missing session id would fall back to)."""
        now = self.counts()
        for name in (f"thread_{agent_id}", f"thread_{agent_id}_default"):
            assert now.get(name, 0) == self.baseline.get(name, 0), f"{name} was written by a Chat turn"


# Loggers whose DEBUG output is driver/transport noise rather than the app's own: left at their level.
QUIET_LOGGERS = ("sqlalchemy", "httpx", "httpcore", "asyncio", "psycopg", "urllib3", "multipart")


@pytest.fixture
def debug_records(monkeypatch):
    """Every record emitted by any logger while the test runs, at DEBUG.

    ``caplog`` alone sees nothing: the app's loggers have their own INFO level and handlers (``utils.logger``). So
    ``Logger.handle`` is wrapped to collect records (loggers created during the request included) and
    ``Logger.setLevel`` is forced to DEBUG for app loggers set up during the test; the loggers that already exist
    are lowered for the duration and restored afterwards.
    """
    records: dict[int, logging.LogRecord] = {}
    original_handle = logging.Logger.handle
    original_set_level = logging.Logger.setLevel

    def quiet(name: str) -> bool:
        return name.split(".")[0] in QUIET_LOGGERS

    def handle(self, record):
        if not quiet(self.name):
            records[id(record)] = record
        return original_handle(self, record)

    requested: dict[int, int] = {}  # level each logger asked for (loggers created during the test keep DEBUG otherwise)

    def set_level(self, level):
        requested[id(self)] = level
        return original_set_level(self, level if quiet(self.name) else logging.DEBUG)

    loggers = [logging.getLogger()] + [
        lg for lg in logging.root.manager.loggerDict.values() if isinstance(lg, logging.Logger)
    ]
    saved = [(lg, lg.level) for lg in loggers]
    monkeypatch.setattr(logging.Logger, "handle", handle)
    monkeypatch.setattr(logging.Logger, "setLevel", set_level)
    for lg in loggers:
        if not quiet(lg.name):
            original_set_level(lg, logging.DEBUG)
    try:
        yield records
    finally:
        known = {id(lg) for lg, _ in saved}
        for lg, level in saved:
            original_set_level(lg, level)
        for lg in logging.root.manager.loggerDict.values():
            if isinstance(lg, logging.Logger) and id(lg) not in known:  # created during the test
                original_set_level(lg, requested.get(id(lg), logging.NOTSET))


# ------------------------------------------------------------------ committed worlds: removal

def purge(engine, *, users=(), apps=(), ai_services=()) -> tuple[list[int], list[int]]:
    """Delete the given roots and every row that reaches them through foreign keys, whatever the cascade rules.

    Also the vector collections of the silos found and the LangGraph threads of the agents found. Runs with FK
    triggers off (the test DB role is a superuser) so the order does not matter; the walk makes sure nothing is left
    referencing a deleted row. Returns the ``(silo ids, agent ids)`` it removed, for ``remaining``.
    """
    tables = list(Base.metadata.sorted_tables)
    seeds = {User.__table__: set(users), App.__table__: set(apps), AIService.__table__: set(ai_services)}
    found: dict[Any, set] = {t: {(i,) for i in ids} for t, ids in seeds.items() if ids}
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("SET LOCAL lock_timeout = '15s'"))  # a stuck lock fails the cleanup, not the whole run
        frontier = set(found)
        while frontier:
            changed: set = set()
            for table in tables:
                for fk in table.foreign_keys:
                    parent = fk.column.table
                    if parent not in frontier or not found.get(parent):
                        continue
                    pk_cols = list(table.primary_key.columns)
                    if not pk_cols:
                        continue
                    parent_pk = list(parent.primary_key.columns)
                    inner = select(fk.column).where(tuple_(*parent_pk).in_(list(found[parent])))
                    rows = conn.execute(select(*pk_cols).where(fk.parent.in_(inner))).all()
                    new = {tuple(r) for r in rows} - found.get(table, set())
                    if new:
                        found.setdefault(table, set()).update(new)
                        changed.add(table)
            frontier = changed

        silo_ids = [pk[0] for pk in found.get(Silo.__table__, ())]
        agent_ids = [pk[0] for pk in found.get(Agent.__table__, ())]
        if silo_ids and conn.execute(text("SELECT to_regclass('langchain_pg_collection')")).scalar():
            names = [f"silo_{i}" for i in silo_ids]
            conn.execute(text(
                "DELETE FROM langchain_pg_embedding WHERE collection_id IN "
                "(SELECT uuid FROM langchain_pg_collection WHERE name = ANY(:n))"), {"n": names})
            conn.execute(text("DELETE FROM langchain_pg_collection WHERE name = ANY(:n)"), {"n": names})
        for agent_id in agent_ids:
            for table in CHECKPOINT_TABLES:
                # The LangGraph tables are created by the checkpointer on first use: absent on a fresh database.
                if conn.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar():
                    conn.execute(text(f"DELETE FROM {table} WHERE thread_id = :exact OR thread_id LIKE :p"),
                                 {"exact": f"thread_{agent_id}", "p": f"thread\\_{agent_id}\\_%"})
        for table, pks in found.items():
            pk_cols = list(table.primary_key.columns)
            ids = list(pks)
            for start in range(0, len(ids), 500):
                conn.execute(table.delete().where(tuple_(*pk_cols).in_(ids[start:start + 500])))
    return silo_ids, agent_ids


def remaining(engine, users, apps, silo_ids=(), agent_ids=()) -> dict:
    """What a finished test left behind: rows of its roots, vector collections of its silos, threads of its agents."""
    with Session(engine) as s:
        left = {
            "users": s.query(User).filter(User.user_id.in_(list(users))).count() if users else 0,
            "apps": s.query(App).filter(App.app_id.in_(list(apps))).count() if apps else 0,
            "collections": 0,
            "threads": 0,
        }
        if silo_ids and s.execute(text("SELECT to_regclass('langchain_pg_collection')")).scalar():
            left["collections"] = s.execute(
                text("SELECT count(*) FROM langchain_pg_collection WHERE name = ANY(:n)"),
                {"n": [f"silo_{i}" for i in silo_ids]},
            ).scalar()
        for agent_id in agent_ids:
            for table in CHECKPOINT_TABLES:
                if s.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar():
                    left["threads"] += s.execute(
                        text(f"SELECT count(*) FROM {table} WHERE thread_id = :exact OR thread_id LIKE :p"),
                        {"exact": f"thread_{agent_id}", "p": f"thread\\_{agent_id}\\_%"},
                    ).scalar()
        return left


LEFTOVER_MIN_AGE = timedelta(minutes=15)


def purge_leftovers_of_killed_runs(engine) -> None:
    """Remove the committed worlds a killed run of the concurrency tests left behind (``cc-...`` users and Apps).

    Only rows OLDER than ``LEFTOVER_MIN_AGE``: a second pytest session on the same database may be running a
    concurrency test right now, and its live (committed) world must not be purged under it.
    """
    cutoff = datetime.now() - LEFTOVER_MIN_AGE
    with Session(engine) as s:
        users = {u for (u,) in s.execute(
            text("SELECT user_id FROM \"User\" WHERE email LIKE 'cc-%@mattin-test.com' AND create_date < :c"),
            {"c": cutoff})}
        apps = {a for (a,) in s.execute(
            text("SELECT app_id FROM \"App\" WHERE name ~ '^cc-(other-)?[0-9a-f]{8}$' AND create_date < :c"),
            {"c": cutoff})}
    if users or apps:
        purge(engine, users=users, apps=apps)
