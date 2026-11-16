"""Isolation of the Chat between users under REAL concurrency (app-flexible-chat step_011).

The product owner's hard requirement is that separate users' interactions never interfere with each other. Step_010
proves it for sequential interactions; this module proves it while turns overlap on the one hidden per-App agent.

Harness (chosen deliberately, see why the existing one cannot be used)
----------------------------------------------------------------------
The sync ``TestClient`` fixtures share ONE test ``Session`` (a connection-level transaction rolled back at teardown)
across every request, and a streamed turn closes that session, so two requests can never overlap on them. Here:

* requests go through ``httpx.AsyncClient`` + ``ASGITransport`` into the real FastAPI app (router, auth, role check,
  ``InternalChatService``, resolver, execution / streaming services, LangGraph checkpointer), all in the test's own
  event loop, launched with ``asyncio.create_task`` / ``asyncio.gather``;
* ``get_db`` is NOT overridden: every request gets its own ``SessionLocal`` session and connection, exactly as in
  production. That means the data is COMMITTED (``cworld``) and removed explicitly afterwards (``purge``: every row
  reachable through a foreign key from the users / Apps / services the test created, the vector collections of their
  silos and the LangGraph threads of their agents), also when a test fails;
* the LangGraph checkpointer pool is opened in the test's loop (the lifespan is not run by ``ASGITransport``);
* the fake model (``GatedModel``) parks every call on per-turn ``asyncio.Event`` gates. A turn is identified by the
  ``[T...]`` tag its message carries. A test holds the tags it wants to overlap, waits until the model was ENTERED for
  all of them, and only then releases them: the interleaving is deterministic (no ``sleep`` ordering), and each test
  asserts on the model's enter / exit sequence numbers that the intervals really overlapped (``assert_overlapped``).
  The scenario runs under ``asyncio.wait_for`` and every gate is opened and every task cancelled on the way out, so a
  deadlock fails in seconds instead of hanging;
* ``httpx``'s ASGI transport hands the response over when the app has finished it, so a streamed response is read
  whole: that is fine here, the overlap happens between requests, inside the model call.

Fakes (same as the other Chat tests, applied at the import site): the LLM (``tools.aiServiceTools.
create_llm_from_service``), the MCP client (``tools.agentTools.MultiServerMCPClient``, records the connections it was
built with, headers included) and the metrics write (``services.agent_metrics_recorder.persist_metrics_payload``). The
retriever is faked too except in ``TestAttachmentsAndTempSiloRag``, which runs the REAL ``get_retriever_tool`` against
a real PGVector collection of the test DB with a deterministic fake embedding model.

Checkpoints survive the schema drop between runs and agent ids restart at 1: threads are asserted through
``ThreadProbe`` baselines, never as absolute "no other thread" statements.
"""
import asyncio
import hashlib
import itertools
import json
import logging
import re
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional

import httpx
import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from sqlalchemy import text
from sqlalchemy.orm import Session

from models.agent import Agent
from models.ai_service import AIService
from models.embedding_service import EmbeddingService
from models.app import App
from models.app_collaborator import CollaborationRole, CollaborationStatus
from models.conversation import Conversation
from models.internal_chat import ChatConversationState, ConversationTurn
from models.mcp_config import MCPConfig
from models.silo import Silo
from models.skill import Skill
from models.usage_record import UsageRecord
from models.repository import Repository
from services.agent_cache_service import CheckpointerCacheService
from services.playground_media_service import PlaygroundMediaService
from tests.factories import (
    AIServiceFactory,
    AppCollaboratorFactory,
    AppFactory,
    EmbeddingServiceFactory,
    UserFactory,
    configure_factories,
)
from tests.integration.internal_chat._chat_support import (
    FakeChatModel,
    FakeMCPClient,
    Recorder,
    ThreadProbe,
    base,
    purge,
    remaining,
    parse_sse,
    selection,
)
from tests.integration.routers.internal._eos_helpers import headers_for

from tools import agentTools as _agent_tools  # noqa: E402  (the REAL retriever builder, captured before any fake)

REAL_GET_RETRIEVER_TOOL = _agent_tools.get_retriever_tool
SCENARIO_TIMEOUT = 60  # seconds: a deadlock must fail, not hang
TAG_RE = re.compile(r"\[(T[A-Za-z0-9_]+)\]")


# ------------------------------------------------------------------ the gated fake model


@dataclass
class ModelCall:
    """One call the fake model received. ``enter`` / ``exit`` are ticks of one shared clock (see ``Turns.tick``)."""

    tag: str
    service_id: int
    messages: list  # [(message type, text)]
    tools: list  # names of the tools bound for this call
    enter: int
    exit: Optional[int] = None
    streamed: bool = False

    @property
    def system(self) -> str:
        return next((content for kind, content in self.messages if kind == "system"), "")

    @property
    def tool_results(self) -> list:
        return [content for kind, content in self.messages if kind == "tool"]

    @property
    def everything(self) -> str:
        return "\n".join(content for _, content in self.messages)


class Turns:
    """Per-turn scheduling of the fake model. A turn is identified by the ``[T...]`` tag of its last human message."""

    def __init__(self):
        self.calls: list[ModelCall] = []
        self._clock = itertools.count(1)
        self._entered: dict[str, asyncio.Event] = {}
        self._released: dict[str, asyncio.Event] = {}
        self.held: set[str] = set()
        self.fail: dict[str, Exception] = {}  # tag -> error the model raises
        self.retrieve: set[str] = set()  # tags whose model calls the temp-silo retriever tool when it is bound

    def tick(self) -> int:
        return next(self._clock)

    @staticmethod
    def tag_of(messages) -> str:
        for message in reversed(messages):
            if message.type == "human":
                found = TAG_RE.search(message.text)
                return found.group(1) if found else "?"
        return "?"

    def _event(self, table: dict, tag: str) -> asyncio.Event:
        return table.setdefault(tag, asyncio.Event())

    def hold(self, *tags: str) -> None:
        self.held.update(tags)

    def entered(self, tag: str) -> asyncio.Event:
        return self._event(self._entered, tag)

    async def wait_entered(self, *tags: str, timeout: float = 20) -> None:
        await asyncio.wait_for(asyncio.gather(*(self.entered(t).wait() for t in tags)), timeout)

    def release(self, *tags: str) -> None:
        for tag in tags:
            self._event(self._released, tag).set()

    def release_all(self) -> None:
        self.release(*self.held, *self._entered, *self._released)

    def of(self, tag: str) -> list[ModelCall]:
        return [c for c in self.calls if c.tag == tag]

    def first(self, tag: str) -> ModelCall:
        calls = self.of(tag)
        assert calls, f"the model never received turn {tag} (saw {[c.tag for c in self.calls]})"
        return calls[0]

    def assert_overlapped(self, *tags: str) -> None:
        """The first model calls of ``tags`` were all inside the model at the same time (no one had left yet)."""
        calls = [self.first(t) for t in tags]
        assert all(c.exit is not None for c in calls), "a held turn never left the model"
        assert max(c.enter for c in calls) < min(c.exit for c in calls), (
            "the turns did not overlap: " + ", ".join(f"{c.tag}=[{c.enter},{c.exit}]" for c in calls)
        )


ANSWER = "reply-{tag} from {service}"


class GatedModel(FakeChatModel):
    """Records each call per turn, parks on the turn's gate and answers ``reply-<tag> from <service id>``.

    ``bind_tools`` returns a COPY carrying the tool names (the base fake stores them per service id, which cannot tell
    two concurrent turns of the same service apart).
    """

    turns: Any
    tool_names: list = []

    def bind_tools(self, tools, **kwargs):
        names = [getattr(t, "name", None) or t.get("name") or t["function"]["name"] for t in tools]
        return self.model_copy(update={"tool_names": names})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # pragma: no cover - would be a harness bug
        raise AssertionError("the sync model path was used; the Chat awaits its model")

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):  # pragma: no cover
        raise AssertionError("the sync model path was used; the Chat awaits its model")

    async def _respond(self, messages, streamed: bool) -> AIMessage:
        turns: Turns = self.turns
        tag = turns.tag_of(messages)
        call = ModelCall(
            tag=tag, service_id=self.service_id, messages=[(m.type, m.text) for m in messages],
            tools=list(self.tool_names), enter=turns.tick(), streamed=streamed,
        )
        turns.calls.append(call)
        turns.entered(tag).set()
        if tag in turns.held:
            await turns._event(turns._released, tag).wait()
        call.exit = turns.tick()
        if tag in turns.fail:
            raise turns.fail[tag]
        last = messages[-1]
        retrievers = [n for n in self.tool_names if n.startswith("playground_content_retriever")]
        if tag in turns.retrieve and retrievers and last.type != "tool":
            return AIMessage(content="", tool_calls=[
                {"name": retrievers[0], "args": {"query": f"find {tag}"}, "id": f"call_{tag}", "type": "tool_call"}
            ])
        return AIMessage(content=ANSWER.format(tag=tag, service=self.service_id))

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=await self._respond(messages, False))])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        result = await self._respond(messages, True)
        if result.tool_calls:
            chunk = AIMessageChunk(content="", tool_call_chunks=[
                {"name": tc["name"], "args": json.dumps(tc["args"]), "id": tc["id"], "index": i}
                for i, tc in enumerate(result.tool_calls)
            ])
            yield ChatGenerationChunk(message=chunk)
            return
        for index, word in enumerate(result.text.split(" ")):
            chunk = AIMessageChunk(content=word if index == 0 else f" {word}")
            if run_manager:
                await run_manager.on_llm_new_token(chunk.text, chunk=ChatGenerationChunk(message=chunk))
            yield ChatGenerationChunk(message=chunk)


class HashEmbeddings(Embeddings):
    """Deterministic bag-of-words embeddings: no provider call, but a real vector in a real collection."""

    DIM = 32

    def _vector(self, value: str) -> list[float]:
        vec = [0.0] * self.DIM
        for word in re.findall(r"[A-Za-z0-9]+", value.lower()):
            vec[int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.DIM] += 1.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, text_):
        return self._vector(text_)

    async def aembed_documents(self, texts):
        return self.embed_documents(texts)

    async def aembed_query(self, text_):
        return self.embed_query(text_)


# ------------------------------------------------------------------ committed world and its removal


@pytest.fixture
def cworld(test_engine):
    """A COMMITTED world (the requests of this module use their own sessions), removed afterwards.

    App ``app`` (alice owns it; bob is an EDITOR and carol a VIEWER) holds three AI services (X, Y, Z), an embedding
    service, silos S1 / S2, skills K1 / K2 / K3, and MCP configs M1 / M2 / M3 (``srv_m1`` ... with their own secret
    header) plus ``boom`` (fails on connect). ``other_app`` (dave) holds a foreign silo / skill / MCP config / model.
    """
    tag = uuid.uuid4().hex[:8]
    roots = {"users": set(), "apps": set(), "ai": set()}
    w = SimpleNamespace(tag=tag, roots=roots)
    session = Session(test_engine)
    try:
        configure_factories(session)

        def user(name):
            u = UserFactory(email=f"cc-{name}-{tag}@mattin-test.com", name=name)
            session.flush()
            roots["users"].add(u.user_id)
            return u

        users = {n: user(n) for n in ("alice", "bob", "carol", "dave")}
        app = AppFactory(owner=users["alice"], name=f"cc-{tag}", slug=f"cc-{tag}")
        other = AppFactory(owner=users["dave"], name=f"cc-other-{tag}", slug=f"cc-other-{tag}")
        session.flush()
        roots["apps"].update({app.app_id, other.app_id})
        AppCollaboratorFactory(app=app, user=users["bob"], role=CollaborationRole.EDITOR,
                               status=CollaborationStatus.ACCEPTED, invited_by=app.owner_id)
        AppCollaboratorFactory(app=app, user=users["carol"], role=CollaborationRole.VIEWER,
                               status=CollaborationStatus.ACCEPTED, invited_by=app.owner_id)
        ai = {n: AIServiceFactory(app=app, name=f"model-{n}-{tag}", description=f"gpt-{n}") for n in "xyz"}
        emb = EmbeddingServiceFactory(app=app)
        other_ai = AIServiceFactory(app=other, name=f"foreign-model-{tag}", description="gpt-foreign")
        other_emb = EmbeddingServiceFactory(app=other)
        session.flush()
        silos = {n: Silo(name=f"silo-{n}-{tag}", app_id=app.app_id, embedding_service_id=emb.service_id)
                 for n in ("s1", "s2")}
        skills = {n: Skill(name=f"skill-{n}-{tag}", description=f"desc {n}", content=f"CONTENT-{n}", app_id=app.app_id)
                  for n in ("k1", "k2", "k3")}

        def conn_cfg(server, **extra):
            return {server: {"url": f"http://{server}.invalid/mcp", "transport": "streamable_http", **extra}}

        mcps = {
            "m1": MCPConfig(name=f"mcp-m1-{tag}", app_id=app.app_id,
                            config=conn_cfg("srv_m1", headers={"X-Api-Key": f"secret-m1-{tag}"})),
            "m2": MCPConfig(name=f"mcp-m2-{tag}", app_id=app.app_id,
                            config=conn_cfg("srv_m2", headers={"X-Api-Key": f"secret-m2-{tag}"})),
            "m3": MCPConfig(name=f"mcp-m3-{tag}", app_id=app.app_id, config=conn_cfg("srv_m3")),
            "boom": MCPConfig(name=f"mcp-boom-{tag}", app_id=app.app_id, config=conn_cfg("boom_srv")),
        }
        foreign = {
            "silo": Silo(name=f"foreign-silo-{tag}", app_id=other.app_id, embedding_service_id=other_emb.service_id),
            "skill": Skill(name=f"foreign-skill-{tag}", content="x", app_id=other.app_id),
            "mcp": MCPConfig(name=f"foreign-mcp-{tag}", app_id=other.app_id, config=conn_cfg("srv_foreign")),
        }
        session.add_all([*silos.values(), *skills.values(), *mcps.values(), *foreign.values()])
        session.flush()
        w.app_id, w.other_app_id = app.app_id, other.app_id
        w.emb = emb.service_id
        w.ai = {n: s.service_id for n, s in ai.items()}
        w.other_ai = other_ai.service_id
        w.silo = {n: s.silo_id for n, s in silos.items()}
        w.skill = {n: s.skill_id for n, s in skills.items()}
        w.skill_name = {n: s.name for n, s in skills.items()}
        w.mcp = {n: m.config_id for n, m in mcps.items()}
        w.foreign = {"silo": foreign["silo"].silo_id, "skill": foreign["skill"].skill_id,
                     "mcp": foreign["mcp"].config_id}
        w.secret = {"m1": f"secret-m1-{tag}", "m2": f"secret-m2-{tag}"}
        w.uid = {n: u.user_id for n, u in users.items()}
        w.h = {n: headers_for(u) for n, u in users.items()}
        w.jwt = {n: h["Authorization"].split(" ", 1)[1] for n, h in w.h.items()}
        session.commit()
        yield w
    finally:
        session.rollback()
        session.close()
        silo_ids, agent_ids = purge(test_engine, users=roots["users"], apps=roots["apps"], ai_services=roots["ai"])
        left = remaining(test_engine, roots["users"], roots["apps"], silo_ids, agent_ids)
        assert left == {"users": 0, "apps": 0, "collections": 0, "threads": 0}, (
            f"the test left committed rows, vector collections or checkpoint threads behind: {left}"
        )


@pytest.fixture
def threads(test_engine):
    return ThreadProbe(test_engine)


# ------------------------------------------------------------------ the stack under test


class Stack:
    """The ASGI client, the fakes and helpers to launch overlapping turns."""

    def __init__(self, client, rec: Recorder, turns: Turns, w, engine):
        self.client, self.rec, self.turns, self.w, self.engine = client, rec, turns, w, engine
        self.tasks: list[asyncio.Task] = []

    # --- requests
    def url(self, path: str = "") -> str:
        return base(self.w.app_id) + path

    async def send(self, who, tag, sel, cid=None, path="/messages", message=None, files=None, refs=None):
        data = {"message": f"[{tag}] {message or 'hello'}", "selection": json.dumps(sel)}
        if cid is not None:
            data["conversation_id"] = str(cid)
        if refs is not None:
            data["file_references"] = json.dumps(refs)
        return await self.client.post(self.url(path), headers=self.w.h[who], data=data, files=files)

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task

    def turn(self, who, tag, sel, cid=None, path="/messages", **kw) -> asyncio.Task:
        """Launch a turn now; the task resolves to a ``Result``."""
        async def run():
            return Result(await self.send(who, tag, sel, cid, path, **kw), path)
        return self.spawn(run())

    async def get(self, who, path, **params):
        return await self.client.get(self.url(path), headers=self.w.h[who], params=params)

    async def detail(self, who, cid) -> dict:
        response = await self.get(who, f"/conversations/{cid}")
        assert response.status_code == 200, response.text
        return response.json()

    async def defaults(self, who) -> dict:
        response = await self.get(who, "/defaults")
        assert response.status_code == 200, response.text
        return response.json()

    async def new_conversation(self, who, sel) -> int:
        response = await self.client.post(self.url("/conversations"), headers=self.w.h[who], json={"selection": sel})
        assert response.status_code == 200, response.text
        return response.json()["conversation_id"]

    async def run(self, scenario, timeout: float = SCENARIO_TIMEOUT):
        """Run ``scenario()`` under a deadline; on the way out every gate opens and every task it spawned is cancelled."""
        try:
            return await asyncio.wait_for(scenario(), timeout)
        finally:
            self.turns.release_all()
            for task in self.tasks:
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)

    # --- database reads (fresh session: only committed data is visible, as for another request)
    def rows(self, fn):
        with Session(self.engine) as s:
            return fn(s)

    def turn_rows(self, cid) -> list[tuple]:
        return self.rows(lambda s: [
            (t.turn_index, t.user_id, t.ai_service_id, t.silo_id, [x["id"] for x in t.skills],
             [x["id"] for x in t.mcp_configs])
            for t in s.query(ConversationTurn).filter_by(conversation_id=cid).order_by(ConversationTurn.turn_index)
        ])

    def conversation_row(self, cid) -> Optional[dict]:
        def read(s):
            row = s.get(Conversation, cid)
            if row is None:
                return None
            return {"agent_id": row.agent_id, "session_id": row.session_id, "user_id": row.user_id,
                    "message_count": row.message_count}
        return self.rows(read)

    def internal_agent_id(self) -> int:
        return self.rows(lambda s: s.query(Agent.agent_id).filter(
            Agent.app_id == self.w.app_id, Agent.kind == "internal_chat").scalar())

    def user_messages(self, detail: dict) -> list[str]:
        return [m["content"] for m in detail["messages"] if m["role"] == "user"]


class Result:
    """One turn's outcome, whether it came over ``/messages`` or ``/stream``."""

    def __init__(self, response: httpx.Response, path: str):
        self.response, self.path = response, path
        self.status = response.status_code
        self.cid = self.turn = self.turn_config = None
        self.text = ""
        self.errors: list[dict] = []
        self.events: list[dict] = []
        if self.status != 200:
            return
        if path == "/messages":
            body = response.json()
            self.cid, self.turn, self.text = body["conversation_id"], body.get("turn"), body["response"]
            self.turn_config = body["metadata"]["turn_config"]
        else:
            self.events = parse_sse(response.text)
            types = [e["type"] for e in self.events]
            assert types and types[0] == "metadata", types
            self.cid = self.events[0]["data"]["conversation_id"]
            self.turn_config = self.events[0]["data"]["turn_config"]
            self.text = "".join(e["data"]["content"] for e in self.events if e["type"] == "token")
            self.errors = [e for e in self.events if e["type"] == "error"]
            done = [e for e in self.events if e["type"] == "done"]
            if done:
                self.turn = done[-1]["data"].get("turn")

    @property
    def failed(self) -> bool:
        return self.status != 200 or bool(self.errors)


@pytest.fixture
async def stack(test_engine, cworld, monkeypatch):
    from main import app

    rec = Recorder()
    turns = Turns()

    def fake_llm(ai_service, temperature=0, is_vision=False):
        return GatedModel(service_id=ai_service.service_id, rec=rec, turns=turns)

    def fake_retriever(silo, *args, **kwargs):
        from langchain_core.tools import StructuredTool

        return StructuredTool.from_function(
            func=lambda query="": "nothing", name=f"retriever_silo_{silo.silo_id}", description="fake retriever"
        )

    async def capture_metrics(payload):
        rec.add_payload(payload)

    mcp_cls = type("BoundFakeMCPClient", (FakeMCPClient,), {"rec": rec})
    monkeypatch.setattr("tools.aiServiceTools.create_llm_from_service", fake_llm)
    monkeypatch.setattr("tools.agentTools.get_retriever_tool", fake_retriever)
    monkeypatch.setattr("tools.agentTools.MultiServerMCPClient", mcp_cls)
    monkeypatch.setattr("services.agent_metrics_recorder.persist_metrics_payload", capture_metrics)

    await CheckpointerCacheService.initialize_pool()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    s = None
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=SCENARIO_TIMEOUT) as client:
            s = Stack(client, rec, turns, cworld, test_engine)
            yield s
    finally:
        if s is not None:
            turns.release_all()
            for task in s.tasks:
                task.cancel()
            await asyncio.gather(*s.tasks, return_exceptions=True)
        await CheckpointerCacheService.close_pool()


# ------------------------------------------------------------------ AC-19 / AC-21 and point 2


def sel_a(w):
    return selection(w.ai["x"], w.silo["s1"], [w.skill["k1"]], [w.mcp["m1"]])


def sel_b(w):
    return selection(w.ai["y"], w.silo["s2"], [w.skill["k2"]], [w.mcp["m2"]])


@pytest.mark.parametrize("path", ["/messages", "/stream"])
async def test_overlapping_turns_of_two_users_each_get_exactly_their_own_configuration(stack, threads, path):
    w, turns = stack.w, stack.turns
    turns.hold("TA", "TB")

    async def scenario():
        ta = stack.turn("bob", "TA", sel_a(w), path=path, message="ALPHA-BODY")
        tb = stack.turn("carol", "TB", sel_b(w), path=path, message="BETA-BODY")
        await turns.wait_entered("TA", "TB")  # both requests are inside the model at the same time
        turns.release("TA", "TB")
        return await ta, await tb

    a, b = await stack.run(scenario)
    turns.assert_overlapped("TA", "TB")
    assert (a.status, b.status) == (200, 200) and not a.errors and not b.errors
    assert a.cid != b.cid

    ca, cb = turns.first("TA"), turns.first("TB")
    # AC-19 model: the X fake only received A's turn, the Y fake only B's
    assert (ca.service_id, cb.service_id) == (w.ai["x"], w.ai["y"])
    assert {c.tag for c in turns.calls if c.service_id == w.ai["x"]} == {"TA"}
    assert {c.tag for c in turns.calls if c.service_id == w.ai["y"]} == {"TB"}
    assert "BETA-BODY" not in ca.everything and "ALPHA-BODY" not in cb.everything
    assert a.text == f"reply-TA from {w.ai['x']}" and b.text == f"reply-TB from {w.ai['y']}"
    # AC-19 retriever / silo, AC-21 MCP tools, skills (names in the prompt + loader tool)
    assert f"retriever_silo_{w.silo['s1']}" in ca.tools and f"retriever_silo_{w.silo['s2']}" not in ca.tools
    assert f"retriever_silo_{w.silo['s2']}" in cb.tools and f"retriever_silo_{w.silo['s1']}" not in cb.tools
    assert "mcp_srv_m1" in ca.tools and "mcp_srv_m2" not in ca.tools
    assert "mcp_srv_m2" in cb.tools and "mcp_srv_m1" not in cb.tools
    assert w.skill_name["k1"] in ca.system and w.skill_name["k2"] not in ca.system
    assert w.skill_name["k2"] in cb.system and w.skill_name["k1"] not in cb.system
    assert "load_skill" in ca.tools and "load_skill" in cb.tools

    # what the client was told, per turn (done.turn / response.metadata.turn_config)
    assert a.turn_config["ai_service"]["id"] == w.ai["x"] and b.turn_config["ai_service"]["id"] == w.ai["y"]
    assert [m["id"] for m in a.turn_config["mcp_configs"]] == [w.mcp["m1"]]
    assert [m["id"] for m in b.turn_config["mcp_configs"]] == [w.mcp["m2"]]
    assert (a.turn["ai_service_id"], a.turn["silo_id"], [s["id"] for s in a.turn["skills"]]) == (
        w.ai["x"], w.silo["s1"], [w.skill["k1"]])
    assert (b.turn["ai_service_id"], b.turn["silo_id"], [s["id"] for s in b.turn["skills"]]) == (
        w.ai["y"], w.silo["s2"], [w.skill["k2"]])
    assert a.turn["turn_index"] == b.turn["turn_index"] == 1

    # stored turn rows, per conversation
    assert stack.turn_rows(a.cid) == [(1, w.uid["bob"], w.ai["x"], w.silo["s1"], [w.skill["k1"]], [w.mcp["m1"]])]
    assert stack.turn_rows(b.cid) == [(1, w.uid["carol"], w.ai["y"], w.silo["s2"], [w.skill["k2"]], [w.mcp["m2"]])]

    # metrics: the right user and the right AI service for each turn
    events = [p["event"] for p in await asyncio.to_thread(stack.rec.wait_payloads, 2)]  # not on the loop
    assert sorted((e["user_id"], e["ai_service_id"]) for e in events) == sorted([
        (w.uid["bob"], w.ai["x"]), (w.uid["carol"], w.ai["y"])])
    assert {e["caller_type"] for e in events} == {"INTERNAL_CHAT"}

    # history, defaults and threads
    assert stack.user_messages(await stack.detail("bob", a.cid)) == ["[TA] ALPHA-BODY"]
    assert stack.user_messages(await stack.detail("carol", b.cid)) == ["[TB] BETA-BODY"]
    assert await stack.defaults("bob") == sel_a(w)
    assert await stack.defaults("carol") == sel_b(w)
    agent_id = stack.internal_agent_id()
    sessions = {stack.conversation_row(c)["session_id"] for c in (a.cid, b.cid)}
    assert threads.of_agent(agent_id) == {f"thread_{agent_id}_{s}" for s in sessions}
    threads.assert_agent_wide_thread_untouched(agent_id)


async def _two_turns_released_in_order(stack, first, second):
    """Wait until both held turns are inside the model, release ``first`` and let it FINISH, then release ``second``."""
    stack.turns.hold(first[1], second[1])
    t1 = stack.turn(*first[0], **first[2])
    t2 = stack.turn(*second[0], **second[2])
    await stack.turns.wait_entered(first[1], second[1])
    stack.turns.release(first[1])
    r1 = await t1
    stack.turns.release(second[1])
    return r1, await t2


async def test_one_user_in_two_tabs_with_different_selections_keeps_each_conversation_separate(stack, threads):
    """AC-20: one user, two conversations, turns overlapping twice (the second round with the selections swapped)."""
    w, turns = stack.w, stack.turns
    one = await stack.new_conversation("alice", sel_a(w))
    two = await stack.new_conversation("alice", sel_b(w))
    turns.hold("TA1", "TB1")

    async def round_one():
        ta = stack.turn("alice", "TA1", sel_a(w), one, message="TAB-ONE-FIRST")
        tb = stack.turn("alice", "TB1", sel_b(w), two, message="TAB-TWO-FIRST")
        await turns.wait_entered("TA1", "TB1")
        turns.release("TA1", "TB1")
        return await ta, await tb

    a1, b1 = await stack.run(round_one)
    turns.assert_overlapped("TA1", "TB1")
    assert (a1.status, b1.status) == (200, 200) and (a1.cid, b1.cid) == (one, two)
    assert (turns.first("TA1").service_id, turns.first("TB1").service_id) == (w.ai["x"], w.ai["y"])
    assert f"retriever_silo_{w.silo['s2']}" not in turns.first("TA1").tools
    assert f"retriever_silo_{w.silo['s1']}" not in turns.first("TB1").tools
    assert "mcp_srv_m2" not in turns.first("TA1").tools and "mcp_srv_m1" not in turns.first("TB1").tools
    assert w.skill_name["k2"] not in turns.first("TA1").system and w.skill_name["k1"] not in turns.first("TB1").system

    # second round: each tab now sends the OTHER selection; the order of completion is fixed (tab two first)
    async def round_two():
        return await _two_turns_released_in_order(
            stack,
            (("alice", "TB2", sel_a(w), two), "TB2", {"message": "TAB-TWO-SECOND"}),
            (("alice", "TA2", sel_b(w), one), "TA2", {"message": "TAB-ONE-SECOND"}),
        )

    b2, a2 = await stack.run(round_two)
    turns.assert_overlapped("TA2", "TB2")
    assert (a2.status, b2.status) == (200, 200)
    call_a2, call_b2 = turns.first("TA2"), turns.first("TB2")
    assert (call_a2.service_id, call_b2.service_id) == (w.ai["y"], w.ai["x"])
    # history: each model call saw its own conversation's earlier message and nothing of the other tab
    assert "TAB-ONE-FIRST" in call_a2.everything and "TAB-TWO-FIRST" not in call_a2.everything
    assert "TAB-TWO-FIRST" in call_b2.everything and "TAB-ONE-FIRST" not in call_b2.everything
    assert "TAB-TWO-SECOND" not in call_a2.everything and "TAB-ONE-SECOND" not in call_b2.everything

    row = lambda cid, ai, silo, skill, mcp, idx: (idx, w.uid["alice"], ai, silo, [skill], [mcp])  # noqa: E731
    assert stack.turn_rows(one) == [row(one, w.ai["x"], w.silo["s1"], w.skill["k1"], w.mcp["m1"], 1),
                                    row(one, w.ai["y"], w.silo["s2"], w.skill["k2"], w.mcp["m2"], 2)]
    assert stack.turn_rows(two) == [row(two, w.ai["y"], w.silo["s2"], w.skill["k2"], w.mcp["m2"], 1),
                                    row(two, w.ai["x"], w.silo["s1"], w.skill["k1"], w.mcp["m1"], 2)]
    d_one, d_two = await stack.detail("alice", one), await stack.detail("alice", two)
    assert stack.user_messages(d_one) == ["[TA1] TAB-ONE-FIRST", "[TA2] TAB-ONE-SECOND"]
    assert stack.user_messages(d_two) == ["[TB1] TAB-TWO-FIRST", "[TB2] TAB-TWO-SECOND"]
    assert d_one["current_selection"] == sel_b(w) and d_two["current_selection"] == sel_a(w)
    # the user's default is the selection of the turn that COMPLETED last (tab one, second round)
    assert await stack.defaults("alice") == sel_b(w)
    agent_id = stack.internal_agent_id()
    sessions = {stack.conversation_row(c)["session_id"] for c in (one, two)}
    assert threads.of_agent(agent_id) == {f"thread_{agent_id}_{s}" for s in sessions}
    assert [stack.conversation_row(c)["message_count"] for c in (one, two)] == [4, 4]


# ------------------------------------------------------------------ AC-22: a turn in flight keeps its own selection


async def test_a_turn_in_flight_finishes_with_its_own_selection_while_another_user_changes_theirs(stack):
    w, turns = stack.w, stack.turns
    app_default_before = await stack.defaults("carol")
    sel_z = selection(w.ai["z"], w.silo["s2"], [w.skill["k3"]], [w.mcp["m3"]])
    turns.hold("TB")

    async def scenario():
        in_flight = stack.turn("carol", "TB", sel_b(w), message="CAROL-IN-FLIGHT")
        await turns.wait_entered("TB")
        # while carol's turn is parked in the model, bob changes selection, saves defaults and completes turns
        put = await stack.client.put(stack.url("/defaults"), headers=w.h["bob"], json=sel_a(w))
        assert put.status_code == 200, put.text
        first = Result(await stack.send("bob", "TA1", sel_a(w), message="BOB-ONE"), "/messages")
        second = Result(await stack.send("bob", "TA2", sel_z, first.cid, message="BOB-TWO"), "/messages")
        put = await stack.client.put(stack.url("/defaults"), headers=w.h["bob"], json=sel_a(w))
        assert put.status_code == 200, put.text
        mid = {"carol_defaults": await stack.defaults("carol"), "turns_of_carol": stack.rows(
            lambda s: s.query(ConversationTurn).filter_by(user_id=w.uid["carol"]).count())}
        assert not in_flight.done(), "carol's turn must still be in flight"
        turns.release("TB")
        return first, second, mid, await in_flight

    first, second, mid, carol = await stack.run(scenario)
    assert (first.status, second.status, carol.status) == (200, 200, 200)
    # nothing bob did reached carol while her turn was in flight
    assert mid["carol_defaults"] == app_default_before and mid["turns_of_carol"] == 0
    # carol's turn: model call, tools, prompt, response metadata, done.turn and the stored row are all hers (Y)
    call = turns.first("TB")
    assert call.service_id == w.ai["y"] and carol.text == f"reply-TB from {w.ai['y']}"
    assert f"retriever_silo_{w.silo['s2']}" in call.tools and "mcp_srv_m2" in call.tools
    assert w.skill_name["k2"] in call.system and w.skill_name["k3"] not in call.system
    assert carol.turn_config["ai_service"]["id"] == w.ai["y"]
    assert carol.turn["ai_service_id"] == w.ai["y"] and [s["id"] for s in carol.turn["skills"]] == [w.skill["k2"]]
    assert stack.turn_rows(carol.cid) == [(1, w.uid["carol"], w.ai["y"], w.silo["s2"], [w.skill["k2"]], [w.mcp["m2"]])]
    assert await stack.defaults("carol") == sel_b(w)
    # bob's turns are bob's (X then Z); his default is what he pinned last (the final PUT, after his turns)
    assert [t[2] for t in stack.turn_rows(first.cid)] == [w.ai["x"], w.ai["z"]]
    assert turns.first("TA1").service_id == w.ai["x"] and turns.first("TA2").service_id == w.ai["z"]
    assert await stack.defaults("bob") == sel_a(w)


# ------------------------------------------------------------------ AC-21 / point 3: MCP between users


@pytest.mark.parametrize("path", ["/messages", "/stream"])
async def test_each_users_token_goes_only_to_the_mcp_configs_that_user_selected(stack, path):
    """bob selects {M1}; carol selects {M1, M2} (M1 is the SAME config); alice selects none. All three overlap."""
    w, turns, rec = stack.w, stack.turns, stack.rec
    turns.hold("TA", "TB", "TC")

    async def scenario():
        ta = stack.turn("bob", "TA", selection(w.ai["x"], mcps=[w.mcp["m1"]]), path=path)
        tb = stack.turn("carol", "TB", selection(w.ai["y"], mcps=[w.mcp["m1"], w.mcp["m2"]]), path=path)
        tc = stack.turn("alice", "TC", selection(w.ai["x"]), path=path)
        await turns.wait_entered("TA", "TB", "TC")
        turns.release("TA", "TB", "TC")
        return [await ta, await tb, await tc]

    results = await stack.run(scenario)
    turns.assert_overlapped("TA", "TB", "TC")
    assert [r.status for r in results] == [200, 200, 200]

    bob_t, carol_t, alice_t = (f"Bearer {w.jwt[n]}" for n in ("bob", "carol", "alice"))
    clients = rec.mcp_clients  # one per turn that selected MCP configs; each is the connections dict it was built with
    assert len(clients) == 2, "one client per turn that selected MCP configs (bob, carol); none for alice"
    by_token = {}
    for connections in clients:
        auths = {cfg["headers"]["Authorization"] for cfg in connections.values()}
        assert len(auths) == 1, f"one client carries one user's token: {auths}"
        by_token[auths.pop()] = connections
    assert set(by_token) == {bob_t, carol_t}, "alice selected nothing: her token reaches no MCP client"
    assert set(by_token[bob_t]) == {"srv_m1"}
    assert set(by_token[carol_t]) == {"srv_m1", "srv_m2"}
    # the provider credential configured on a config is kept and never crosses to a config that does not own it
    assert by_token[bob_t]["srv_m1"]["headers"]["X-Api-Key"] == w.secret["m1"]
    assert by_token[carol_t]["srv_m1"]["headers"]["X-Api-Key"] == w.secret["m1"]
    assert by_token[carol_t]["srv_m2"]["headers"]["X-Api-Key"] == w.secret["m2"]
    assert w.secret["m2"] not in json.dumps(by_token[bob_t])
    everything = json.dumps(clients)
    for name in ("m3", "boom"):
        assert f"srv_{name}" not in everything and "boom_srv" not in everything, "an unselected config got a client"
    assert w.jwt["alice"] not in everything and w.jwt["dave"] not in everything
    # and each model only got the tools of its own set
    assert [t for t in turns.first("TA").tools if t.startswith("mcp_")] == ["mcp_srv_m1"]
    assert sorted(t for t in turns.first("TB").tools if t.startswith("mcp_")) == ["mcp_srv_m1", "mcp_srv_m2"]
    assert not [t for t in turns.first("TC").tools if t.startswith("mcp_")]


async def test_a_foreign_apps_mcp_config_is_refused_and_never_gets_a_client_or_a_token(stack):
    w, turns, rec = stack.w, stack.turns, stack.rec
    turns.hold("TB")

    async def scenario():
        ok = stack.turn("carol", "TB", selection(w.ai["y"], mcps=[w.mcp["m2"]]))
        await turns.wait_entered("TB")
        refused = await stack.send("bob", "TA", selection(w.ai["x"], mcps=[w.mcp["m1"], w.foreign["mcp"]]))
        mixed = await stack.send("bob", "TA2", selection(w.ai["x"], mcps=[w.foreign["mcp"]]), path="/stream")
        turns.release("TB")
        return refused, mixed, await ok

    refused, mixed, ok = await stack.run(scenario)
    assert refused.status_code == 404 and mixed.status_code == 404
    assert refused.json() == {"detail": "Resource not found", "error_code": "NOT_FOUND"}
    assert turns.of("TA") == [] and turns.of("TA2") == [], "a refused turn never reaches the model"
    assert ok.status == 200
    assert len(rec.mcp_clients) == 1 and set(rec.mcp_clients[0]) == {"srv_m2"}, "only carol's own selection built a client"
    assert w.jwt["bob"] not in json.dumps(rec.mcp_clients)


async def test_an_mcp_failure_of_one_turn_shows_up_only_in_that_turns_warnings(stack):
    w, turns = stack.w, stack.turns
    turns.hold("TA", "TB")
    warning = {"kind": "mcp_config", "id": w.mcp["boom"]}

    async def scenario():
        ta = stack.turn("bob", "TA", selection(w.ai["x"], mcps=[w.mcp["boom"]]), path="/stream")
        tb = stack.turn("carol", "TB", selection(w.ai["y"], mcps=[w.mcp["m2"]]), path="/stream")
        await turns.wait_entered("TA", "TB")
        turns.release("TA", "TB")
        return await ta, await tb

    a, b = await stack.run(scenario)
    turns.assert_overlapped("TA", "TB")
    assert (a.status, b.status) == (200, 200) and not a.errors and not b.errors
    # turn_config.warnings lists configs skipped before the run; a server that fails to connect is reported in turn.warnings
    assert a.turn_config["warnings"] == [] and b.turn_config["warnings"] == []
    assert a.turn["warnings"] == [warning] and b.turn["warnings"] == []
    assert not [t for t in turns.first("TA").tools if t.startswith("mcp_")], "boom's client failed as a whole"
    assert "mcp_srv_m2" in turns.first("TB").tools, "carol's MCP tools are unaffected by bob's failing server"
    # what the user asked for is remembered (including the failing config), per user
    assert [t[5] for t in stack.turn_rows(a.cid)] == [[w.mcp["boom"]]]
    assert [t[5] for t in stack.turn_rows(b.cid)] == [[w.mcp["m2"]]]
    assert (await stack.detail("carol", b.cid))["warnings"] == []


# ------------------------------------------------------------------ point 6: a failing turn leaves the others alone


@pytest.mark.parametrize("path", ["/messages", "/stream"])
@pytest.mark.parametrize("failure", ["model_error", "mcp_error"])
async def test_a_failing_turn_does_not_affect_another_users_turn_in_flight(stack, path, failure):
    w, turns = stack.w, stack.turns
    # bob has a conversation with one successful turn; carol's turn is parked in the model while bob's turn fails
    first = Result(await stack.send("bob", "T0", sel_a(w), message="BOB-BEFORE"), "/messages")
    assert first.status == 200
    bob_before = {"turns": stack.turn_rows(first.cid), "row": stack.conversation_row(first.cid),
                  "default": await stack.defaults("bob"), "history": stack.user_messages(await stack.detail("bob", first.cid))}
    sel_bad = sel_b(w) if failure == "model_error" else selection(w.ai["x"], mcps=[w.mcp["boom"]])
    if failure == "model_error":
        turns.fail["TA"] = RuntimeError("fake llm failure")
    turns.hold("TB")

    async def scenario():
        carol = stack.turn("carol", "TB", sel_b(w), path=path, message="CAROL-OK")
        await turns.wait_entered("TB")
        failing = Result(await stack.send("bob", "TA", sel_bad, first.cid, path=path, message="BOB-FAILS"), path)
        assert not carol.done(), "carol's turn must still be in flight when bob's turn ends"
        turns.release("TB")
        return failing, await carol

    failing, carol = await stack.run(scenario)
    assert carol.status == 200 and not carol.errors and carol.text == f"reply-TB from {w.ai['y']}"
    assert carol.turn["ai_service_id"] == w.ai["y"] and carol.turn["warnings"] == []
    assert stack.turn_rows(carol.cid) == [(1, w.uid["carol"], w.ai["y"], w.silo["s2"], [w.skill["k2"]], [w.mcp["m2"]])]
    assert await stack.defaults("carol") == sel_b(w)
    assert (await stack.detail("carol", carol.cid))["warnings"] == []
    if failure == "model_error":
        assert failing.failed, "bob's turn must have failed"
        # a failed turn writes nothing of bob's: no turn row, no default change, history and counters as before
        assert stack.turn_rows(first.cid) == bob_before["turns"]
        assert stack.conversation_row(first.cid) == bob_before["row"]
        assert await stack.defaults("bob") == bob_before["default"]
        # the checkpointer keeps the unanswered message (as in the playground); it is bob's own history only
        assert stack.user_messages(await stack.detail("bob", first.cid)) == bob_before["history"] + ["[TA] BOB-FAILS"]
        assert "BOB-FAILS" not in "".join(stack.user_messages(await stack.detail("carol", carol.cid)))
    else:
        # an unreachable MCP server degrades bob's turn (warning, no MCP tools): it neither fails nor touches carol
        assert not failing.failed and failing.turn["warnings"] == [{"kind": "mcp_config", "id": w.mcp["boom"]}]
        assert [c.service_id for c in turns.of("TA")] == [w.ai["x"]]
        assert not [t for t in turns.first("TA").tools if t.startswith("mcp_")]


# ------------------------------------------------------------------ NFR-6 / races on one conversation


async def _wait_until(predicate, what: str, timeout: float = 15.0) -> None:
    """Wait for background cleanup (thread deletes run as background tasks) with a deadline; it orders nothing."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < deadline, f"timed out waiting for: {what}"
        await asyncio.sleep(0.05)


def busy_of(stack, cid) -> Optional[tuple]:
    """``(busy_token, busy_until)`` of a conversation's state row (committed data), None when the row is gone."""
    return stack.rows(lambda s: (lambda r: None if r is None else (r.busy_token, r.busy_until))(
        s.get(ChatConversationState, cid)))


def assert_free(stack, cid) -> None:
    assert busy_of(stack, cid) == (None, None), f"the conversation is still marked busy: {busy_of(stack, cid)}"


async def _busy_scenario(stack, path):
    """bob answers one turn, parks a second one in the model (TA) and sends a third (TB) on the SAME conversation."""
    w, turns = stack.w, stack.turns
    first = Result(await stack.send("bob", "T0", sel_a(w), message="FIRST"), "/messages")
    assert first.status == 200
    cid = first.cid
    before = {
        "turns": stack.turn_rows(cid), "row": stack.conversation_row(cid), "default": await stack.defaults("bob"),
    }
    agent_id = before["row"]["agent_id"]
    turns.hold("TA")

    async def scenario():
        ta = stack.turn("bob", "TA", sel_a(w), cid, path=path, message="TAB-A")
        await turns.wait_entered("TA")
        assert busy_of(stack, cid)[0] is not None, "the turn in flight holds the conversation"
        refused = await stack.send("bob", "TB", sel_b(w), cid, path=path, message="TAB-B")
        mid = {
            "turns": stack.turn_rows(cid), "row": stack.conversation_row(cid), "default": await stack.defaults("bob"),
        }
        turns.release("TA")
        return first, refused, mid, await ta

    return agent_id, before, await stack.run(scenario)


@pytest.mark.parametrize("path", ["/messages", "/stream"])
async def test_a_second_turn_on_a_busy_conversation_is_refused_with_409_and_writes_nothing(stack, threads, path):
    """NFR-6: one turn at a time per conversation. The refusal is a real HTTP 409 (also for /stream: no SSE), it
    carries Retry-After, and it leaves no trace; the first turn completes and the history keeps both messages."""
    w, turns = stack.w, stack.turns
    agent_id, before, (first, refused, mid, a) = await _busy_scenario(stack, path)
    cid = first.cid
    assert refused.status_code == 409, refused.text
    assert refused.json()["error_code"] == "CONVERSATION_BUSY" and refused.json()["detail"]
    assert int(refused.headers["retry-after"]) > 0
    assert "text/event-stream" not in refused.headers.get("content-type", "")
    # nothing was written for the refused turn: no model call, no turn row, counters, default or thread change
    assert turns.of("TB") == []
    assert mid["turns"] == before["turns"] and mid["row"] == before["row"] and mid["default"] == before["default"]
    # the first turn completes and the history is intact
    assert a.status == 200 and not a.errors and a.turn["turn_index"] == 2
    assert stack.user_messages(await stack.detail("bob", cid)) == ["[T0] FIRST", "[TA] TAB-A"]
    assert [r[0] for r in stack.turn_rows(cid)] == [1, 2]
    assert stack.conversation_row(cid)["message_count"] == 4
    assert await stack.defaults("bob") == sel_a(w), "the refused turn's selection (B) did not become the default"
    session = stack.conversation_row(cid)["session_id"]
    assert threads.of_agent(agent_id) == {f"thread_{agent_id}_{session}"}
    assert_free(stack, cid)
    # a third turn afterwards succeeds
    third = Result(await stack.send("bob", "TC", sel_b(w), cid, path=path, message="TAB-C"), path)
    assert third.status == 200 and third.turn["turn_index"] == 3
    assert stack.user_messages(await stack.detail("bob", cid)) == ["[T0] FIRST", "[TA] TAB-A", "[TC] TAB-C"]
    assert_free(stack, cid)


@pytest.mark.parametrize("path", ["/messages", "/stream"])
async def test_the_marker_is_released_after_a_failed_turn(stack, path):
    w, turns = stack.w, stack.turns
    first = Result(await stack.send("bob", "T0", sel_a(w), message="FIRST"), "/messages")
    turns.fail["TA"] = RuntimeError("fake llm failure")
    failed = Result(await stack.send("bob", "TA", sel_a(w), first.cid, path=path, message="BOOM"), path)
    assert failed.failed
    assert_free(stack, first.cid)
    again = Result(await stack.send("bob", "TB", sel_a(w), first.cid, path=path, message="RETRY"), path)
    assert again.status == 200 and not again.errors


@pytest.mark.parametrize("path", ["/messages", "/stream"])
async def test_the_marker_is_released_when_the_selection_is_invalid_after_the_claim(stack, path):
    w = stack.w
    first = Result(await stack.send("bob", "T0", sel_a(w), message="FIRST"), "/messages")
    refused = await stack.send("bob", "TX", selection(w.other_ai), first.cid, path=path)  # a foreign model: 404
    assert refused.status_code == 404
    assert_free(stack, first.cid)


@pytest.mark.parametrize("path", ["/messages", "/stream"])
async def test_the_marker_is_released_after_a_retired_service_409(stack, test_engine, path):
    from datetime import datetime, timedelta, timezone

    w = stack.w
    first = Result(await stack.send("bob", "T0", sel_a(w), message="FIRST"), "/messages")
    with Session(test_engine) as s:
        s.get(AIService, w.ai["y"]).end_of_service_at = datetime.now(timezone.utc) - timedelta(days=1)
        s.commit()
    refused = await stack.send("bob", "TR", sel_b(w), first.cid, path=path)
    assert refused.status_code == 409 and refused.json()["error_code"] == "SERVICE_RETIRED"
    assert_free(stack, first.cid)
    assert (await stack.send("bob", "TOK", sel_a(w), first.cid, path=path)).status_code == 200


async def test_a_first_streaming_turn_that_fails_discards_its_conversation_and_leaves_no_marker(stack):
    w, turns = stack.w, stack.turns
    turns.fail["TF"] = RuntimeError("fake llm failure")
    failed = Result(await stack.send("bob", "TF", sel_a(w), None, path="/stream", message="FIRST-FAILS"), "/stream")
    assert failed.errors and failed.cid is not None
    assert stack.conversation_row(failed.cid) is None, "the empty conversation of the failed first turn was dropped"
    assert busy_of(stack, failed.cid) is None
    assert Result(await stack.send("bob", "TG", sel_a(w), None, path="/stream"), "/stream").status == 200


async def test_an_expired_marker_can_be_claimed_and_a_live_one_cannot(stack, test_engine):
    from datetime import datetime, timedelta, timezone

    w = stack.w
    first = Result(await stack.send("bob", "T0", sel_a(w), message="FIRST"), "/messages")
    cid = first.cid

    def mark(delta):
        with Session(test_engine) as s:
            row = s.get(ChatConversationState, cid)
            row.busy_token, row.busy_until = uuid.uuid4(), datetime.now(timezone.utc) + delta
            s.commit()

    mark(timedelta(minutes=10))  # a crashed turn that has not expired yet
    assert (await stack.send("bob", "T1", sel_a(w), cid)).status_code == 409
    mark(-timedelta(seconds=5))  # expired
    assert (await stack.send("bob", "T2", sel_a(w), cid)).status_code == 200
    assert_free(stack, cid)


async def test_a_reset_during_a_turn_clears_the_marker_and_the_stale_turn_neither_blocks_nor_writes(stack):
    w, turns = stack.w, stack.turns
    first = Result(await stack.send("bob", "T0", sel_a(w), message="BEFORE-RESET"), "/messages")
    cid = first.cid
    turns.hold("TA")

    async def scenario():
        stale = stack.turn("bob", "TA", sel_b(w), cid, message="STALE-TURN")
        await turns.wait_entered("TA")
        assert busy_of(stack, cid)[0] is not None
        reset = await stack.client.post(stack.url(f"/conversations/{cid}/reset"), headers=w.h["bob"])
        assert reset.status_code == 200, reset.text
        assert_free(stack, cid)  # reset always wins
        fresh = Result(await stack.send("bob", "TC", sel_a(w), cid, message="AFTER-RESET"), "/messages")
        assert fresh.status == 200 and fresh.turn["turn_index"] == 1, "the stale turn does not block the new generation"
        turns.release("TA")
        return fresh, await stale

    fresh, stale = await stack.run(scenario)
    assert stale.status == 200 and stale.turn is None
    assert stack.user_messages(await stack.detail("bob", cid)) == ["[TC] AFTER-RESET"]
    assert [r[0] for r in stack.turn_rows(cid)] == [1]
    assert_free(stack, cid)  # the stale turn's release matched nothing (it must not clear a newer claim either)


async def test_a_stale_release_does_not_clear_a_newer_claim(stack):
    w, turns = stack.w, stack.turns
    first = Result(await stack.send("bob", "T0", sel_a(w), message="FIRST"), "/messages")
    cid = first.cid
    turns.hold("TA", "TC")

    async def scenario():
        stale = stack.turn("bob", "TA", sel_a(w), cid, message="STALE")
        await turns.wait_entered("TA")
        reset = await stack.client.post(stack.url(f"/conversations/{cid}/reset"), headers=w.h["bob"])
        assert reset.status_code == 200
        newer = stack.turn("bob", "TC", sel_a(w), cid, message="NEWER")
        await turns.wait_entered("TC")
        token = busy_of(stack, cid)[0]
        assert token is not None
        turns.release("TA")
        await stale
        assert busy_of(stack, cid)[0] == token, "the stale turn released the NEWER turn's claim"
        assert (await stack.send("bob", "TD", sel_a(w), cid)).status_code == 409
        turns.release("TC")
        return await newer

    assert (await stack.run(scenario)).status == 200
    assert_free(stack, cid)


async def test_a_delete_during_a_turn_leaves_no_marker_or_row(stack):
    w, turns = stack.w, stack.turns
    first = Result(await stack.send("bob", "T0", sel_a(w), message="FIRST"), "/messages")
    cid = first.cid
    turns.hold("TA")

    async def scenario():
        stale = stack.turn("bob", "TA", sel_a(w), cid)
        await turns.wait_entered("TA")
        assert (await stack.client.delete(stack.url(f"/conversations/{cid}"), headers=w.h["bob"])).status_code == 204
        turns.release("TA")
        return await stale

    assert (await stack.run(scenario)).status == 200
    assert busy_of(stack, cid) is None


async def test_other_conversations_and_other_users_are_never_blocked_by_a_turn_in_flight(stack):
    w, turns = stack.w, stack.turns
    c1 = await stack.new_conversation("bob", sel_a(w))
    c2 = await stack.new_conversation("bob", sel_a(w))
    c3 = await stack.new_conversation("carol", sel_b(w))
    turns.hold("T1", "T2", "T3")

    async def scenario():
        t1 = stack.turn("bob", "T1", sel_a(w), c1)
        t2 = stack.turn("bob", "T2", sel_a(w), c2)
        t3 = stack.turn("carol", "T3", sel_b(w), c3)
        await turns.wait_entered("T1", "T2", "T3")
        for cid in (c1, c2, c3):
            assert busy_of(stack, cid)[0] is not None
        turns.release("T1", "T2", "T3")
        return [await t for t in (t1, t2, t3)]

    results = await stack.run(scenario)
    turns.assert_overlapped("T1", "T2", "T3")
    assert [r.status for r in results] == [200, 200, 200]
    for cid in (c1, c2, c3):
        assert_free(stack, cid)


async def test_closing_the_stream_mid_turn_releases_the_marker_at_once(stack):
    """A client that hangs up (the generator is closed while the turn is in flight) frees the conversation: the
    release is synchronous in the generator's ``finally``, with no ``await`` before it."""
    from starlette.requests import Request

    from db.database import SessionLocal
    from routers.internal.internal_chat import chat_stream

    w, turns = stack.w, stack.turns
    first = Result(await stack.send("bob", "T0", sel_a(w), message="FIRST"), "/messages")
    cid = first.cid
    turns.hold("TA")
    db = SessionLocal()
    try:
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
        auth = SimpleNamespace(identity=SimpleNamespace(id=str(w.uid["bob"]), email=f"cc-bob-{w.tag}@mattin-test.com"))
        response = await chat_stream(
            app_id=w.app_id, request=request, message="[TA] hang up", selection=json.dumps(sel_a(w)),
            auth_context=auth, role=None, db=db, _=None, conversation_id=cid, files=None,
            file_references=None, search_params=None,
        )
        iterator = response.body_iterator
        assert busy_of(stack, cid)[0] is not None, "claimed before the stream started"
        assert "metadata" in await asyncio.wait_for(iterator.__anext__(), 20)
        await iterator.aclose()
        assert_free(stack, cid)
    finally:
        turns.release_all()
        db.close()
    # the conversation is usable again
    assert (await stack.send("bob", "TB", sel_a(w), cid)).status_code == 200


async def test_a_reset_racing_a_turn_leaves_the_stale_turn_out_of_the_new_generation(stack, threads):
    w, turns = stack.w, stack.turns
    first = Result(await stack.send("bob", "T0", sel_a(w), message="BEFORE-RESET"), "/messages")
    cid = first.cid
    before = stack.conversation_row(cid)
    agent_id = before["agent_id"]
    old_thread = f"thread_{agent_id}_{before['session_id']}"
    turns.hold("TA")

    async def scenario():
        stale = stack.turn("bob", "TA", sel_b(w), cid, message="STALE-TURN")
        await turns.wait_entered("TA")
        reset = await stack.client.post(stack.url(f"/conversations/{cid}/reset"), headers=w.h["bob"])
        assert reset.status_code == 200, reset.text
        turns.release("TA")
        return await stale

    stale = await stack.run(scenario)
    assert stale.status == 200 and stale.text == f"reply-TA from {w.ai['y']}", "the stale turn still answers its caller"
    assert stale.turn is None, "but it persists no turn snapshot into the new generation"
    after = stack.conversation_row(cid)
    assert after["session_id"] != before["session_id"]
    assert stack.turn_rows(cid) == []
    state = stack.rows(lambda s: s.get(ChatConversationState, cid).generation)
    assert state >= 1
    assert await stack.defaults("bob") == sel_a(w), "a stale turn does not move the user's default"
    assert (await stack.detail("bob", cid))["messages"] == []
    # the thread the stale turn wrote to is no longer referenced and is dropped in the background
    await _wait_until(lambda: threads.rows(old_thread) == 0, "the old thread of the reset conversation is gone")
    # the new generation works and starts at turn 1 with a clean history
    third = Result(await stack.send("bob", "TC", sel_a(w), cid, message="AFTER-RESET"), "/messages")
    assert third.status == 200 and third.turn["turn_index"] == 1
    call = turns.first("TC")
    assert "STALE-TURN" not in call.everything and "BEFORE-RESET" not in call.everything
    assert stack.user_messages(await stack.detail("bob", cid)) == ["[TC] AFTER-RESET"]
    assert threads.rows(old_thread) == 0
    # Known limit (documented on ``reset_conversation``): the stale turn had already counted its two messages before the
    # reset zeroed the counters, so they show again; the turn after the reset adds its own two.
    assert stack.conversation_row(cid)["message_count"] == 4


async def test_a_delete_racing_a_turn_leaves_nothing_behind(stack, threads):
    w, turns = stack.w, stack.turns
    first = Result(await stack.send("bob", "T0", sel_a(w), message="BEFORE-DELETE"), "/messages")
    cid = first.cid
    before = stack.conversation_row(cid)
    agent_id = before["agent_id"]
    old_thread = f"thread_{agent_id}_{before['session_id']}"
    turns.hold("TA")

    async def scenario():
        stale = stack.turn("bob", "TA", sel_b(w), cid, message="DOOMED-TURN")
        await turns.wait_entered("TA")
        deleted = await stack.client.delete(stack.url(f"/conversations/{cid}"), headers=w.h["bob"])
        assert deleted.status_code == 204, deleted.text
        turns.release("TA")
        return await stale

    stale = await stack.run(scenario)
    assert stale.status == 200 and stale.text == f"reply-TA from {w.ai['y']}"
    assert stale.turn is None
    assert stack.conversation_row(cid) is None
    assert stack.turn_rows(cid) == []
    assert stack.rows(lambda s: s.get(ChatConversationState, cid)) is None
    assert (await stack.get("bob", f"/conversations/{cid}")).status_code == 404
    assert await stack.defaults("bob") == sel_a(w)
    await _wait_until(lambda: threads.rows(old_thread) == 0, "the thread of the deleted conversation is gone")




# ------------------------------------------------------------------ AC-24 / point 5: attachments and temp-silo RAG
# The REAL ``get_retriever_tool`` runs against a real PGVector collection of the test DB; only the embedding model is a
# deterministic fake (``HashEmbeddings``). The similarity search returns every chunk of a collection (k=10, a handful
# of chunks), so what a turn retrieves is decided by WHICH collection its retriever points at: exactly what must be
# isolated.

A_FILE, B_FILE = "zebra-aaa.txt", "quokka-bbb.txt"
A_MARK, B_MARK = "ZEBRA-AAA-91x", "QUOKKA-BBB-47y"


class Rag(SimpleNamespace):
    pass


@pytest.fixture
async def rag(stack, monkeypatch):
    """bob: conversation ``a1`` (uploads A_FILE, indexed) and ``a2`` (nothing). carol: ``b1`` (uploads B_FILE, indexed)."""
    w = stack.w
    monkeypatch.setattr("tools.agentTools.get_retriever_tool", REAL_GET_RETRIEVER_TOOL)
    monkeypatch.setattr("tools.vector_stores.pgvector_store.get_embeddings_model", lambda svc: HashEmbeddings())
    with Session(stack.engine) as session:  # the product's own path: the App's default embedding service
        session.get(App, w.app_id).default_embedding_service_id = w.emb
        session.commit()
    out = Rag(a1=await stack.new_conversation("bob", selection(w.ai["x"])),
              a2=await stack.new_conversation("bob", selection(w.ai["x"])),
              b1=await stack.new_conversation("carol", selection(w.ai["y"])))

    async def attach(who, cid, filename, mark):
        body = f"{mark} is the codeword of this document. {mark} appears here. Remember {mark}."
        response = await stack.client.post(
            stack.url(f"/conversations/{cid}/files"), headers=w.h[who], files={"file": (filename, body.encode(), "text/plain")}
        )
        assert response.status_code == 200, response.text
        assert response.json()["vectorized"] is True, "the upload indexed the file into the conversation's temp silo"
        return response.json()["file_id"]

    out.a1_file = await attach("bob", out.a1, A_FILE, A_MARK)
    out.b1_file = await attach("carol", out.b1, B_FILE, B_MARK)
    # The collections the uploads created hold ONLY their own file (silo ids restart at 1 across runs, and the
    # vector tables survive the schema drop: a stale ``silo_<id>`` collection would otherwise leak into the asserts).
    for cid, mark in ((out.a1, A_MARK), (out.b1, B_MARK)):
        (silo_id,) = temp_silo_ids(stack, cid)
        texts = collection_texts(stack, silo_id)
        assert texts and all(mark in t for t in texts), f"collection silo_{silo_id} did not start empty: {texts}"
    return out


def temp_silo_ids(stack, cid) -> list[int]:
    row = stack.conversation_row(cid)
    return stack.rows(lambda s: PlaygroundMediaService.get_temp_silo_ids_for_agent(
        stack.w.app_id, row["agent_id"], row["session_id"], s))


def collection_texts(stack, silo_id) -> list[str]:
    with stack.engine.connect() as conn:
        return [r[0] for r in conn.execute(text(
            "SELECT e.document FROM langchain_pg_embedding e JOIN langchain_pg_collection c "
            "ON c.uuid = e.collection_id WHERE c.name = :n"), {"n": f"silo_{silo_id}"})]


@pytest.mark.parametrize("path", ["/messages", "/stream"])
async def test_an_attachment_is_retrieved_only_by_the_turns_of_its_own_conversation(stack, rag, path):
    w, turns = stack.w, stack.turns
    a1_silo, b1_silo = temp_silo_ids(stack, rag.a1), temp_silo_ids(stack, rag.b1)
    assert len(a1_silo) == 1 and len(b1_silo) == 1 and a1_silo != b1_silo
    assert temp_silo_ids(stack, rag.a2) == [], "a second conversation of the SAME user has no temp silo"
    # the collections really hold each file's chunks, and only those
    assert collection_texts(stack, a1_silo[0]) and all(A_MARK in t and B_MARK not in t for t in collection_texts(stack, a1_silo[0]))
    assert collection_texts(stack, b1_silo[0]) and all(B_MARK in t and A_MARK not in t for t in collection_texts(stack, b1_silo[0]))

    turns.hold("TA1", "TA2", "TB1")
    turns.retrieve.update({"TA1", "TA2", "TB1"})

    async def scenario():
        t1 = stack.turn("bob", "TA1", selection(w.ai["x"]), rag.a1, path=path, message="what is the codeword")
        t2 = stack.turn("bob", "TA2", selection(w.ai["x"]), rag.a2, path=path, message="what is the codeword")
        t3 = stack.turn("carol", "TB1", selection(w.ai["y"]), rag.b1, path=path, message="what is the codeword")
        await turns.wait_entered("TA1", "TA2", "TB1")
        turns.release("TA1", "TA2", "TB1")
        return await t1, await t2, await t3

    a1, a2, b1 = await stack.run(scenario)
    turns.assert_overlapped("TA1", "TA2", "TB1")
    assert [r.status for r in (a1, a2, b1)] == [200, 200, 200] and not (a1.errors or a2.errors or b1.errors)

    def retriever_tools(tag):
        return [t for t in turns.first(tag).tools if t.startswith("playground_content_retriever")]

    assert retriever_tools("TA1") == ["playground_content_retriever_0"]
    assert retriever_tools("TB1") == ["playground_content_retriever_0"]
    assert retriever_tools("TA2") == []
    # what the REAL retriever returned to each model (second call of the turn carries the tool result)
    a_results = " ".join(r for c in turns.of("TA1") for r in c.tool_results)
    b_results = " ".join(r for c in turns.of("TB1") for r in c.tool_results)
    assert A_MARK in a_results and B_MARK not in a_results
    assert B_MARK in b_results and A_MARK not in b_results
    # nothing of the other conversation (file name, content) in anything a model received
    everything = lambda tag: " ".join(c.everything for c in turns.of(tag))  # noqa: E731
    assert B_MARK not in everything("TA1") and B_FILE not in everything("TA1")
    assert A_MARK not in everything("TB1") and A_FILE not in everything("TB1")
    assert A_MARK not in everything("TA2") and B_MARK not in everything("TA2")
    assert A_FILE not in everything("TA2"), "bob's other conversation does not see bob's attachment either"
    assert A_FILE in everything("TA1") and B_FILE in everything("TB1"), "positive control: own file is announced"


async def test_file_references_to_another_conversations_file_are_dropped(stack, rag):
    w, turns = stack.w, stack.turns
    turns.hold("TB", "TA2")
    turns.retrieve.update({"TB", "TA2"})

    async def scenario():
        # carol points at bob's file id from her own conversation; bob points at his own a1 file from a2
        carol = stack.turn("carol", "TB", selection(w.ai["y"]), rag.b1, refs=[rag.a1_file, rag.b1_file], message="use these")
        bob = stack.turn("bob", "TA2", selection(w.ai["x"]), rag.a2, refs=[rag.a1_file], message="use this")
        await turns.wait_entered("TB", "TA2")
        turns.release("TB", "TA2")
        return await carol, await bob

    carol, bob = await stack.run(scenario)
    assert (carol.status, bob.status) == (200, 200)
    seen_by_carol = " ".join(c.everything for c in turns.of("TB"))
    assert A_FILE not in seen_by_carol and A_MARK not in seen_by_carol
    assert B_FILE in seen_by_carol, "her own referenced file is kept"
    assert B_MARK in " ".join(r for c in turns.of("TB") for r in c.tool_results)
    seen_by_bob = " ".join(c.everything for c in turns.of("TA2"))
    assert A_FILE not in seen_by_bob and A_MARK not in seen_by_bob, "a file of another conversation is dropped, even bob's own"
    assert not [t for t in turns.first("TA2").tools if t.startswith("playground_content_retriever")]


async def test_cleaning_up_one_conversations_temp_silo_leaves_the_other_intact(stack, rag):
    w, turns = stack.w, stack.turns
    a1_silo, b1_silo = temp_silo_ids(stack, rag.a1)[0], temp_silo_ids(stack, rag.b1)[0]
    b_chunks = collection_texts(stack, b1_silo)
    assert b_chunks

    deleted = await stack.client.delete(stack.url(f"/conversations/{rag.a1}"), headers=w.h["bob"])
    assert deleted.status_code == 204

    def temp_repos():
        return stack.rows(lambda s: sorted(r.silo_id for r in s.query(Repository).filter(
            Repository.app_id == w.app_id, Repository.name.like("%playground%"))))

    assert temp_repos() == [b1_silo], "only the deleted conversation's temp repository / silo went away"
    assert collection_texts(stack, a1_silo) == [] and collection_texts(stack, b1_silo) == b_chunks
    # and carol's conversation still retrieves her file
    turns.retrieve.add("TB")
    result = Result(await stack.send("carol", "TB", selection(w.ai["y"]), rag.b1, message="again"), "/messages")
    assert result.status == 200
    assert B_MARK in " ".join(r for c in turns.of("TB") for r in c.tool_results)

    # a reset of carol's conversation drops only ITS temp silo; bob's remaining conversation is untouched
    reset = await stack.client.post(stack.url(f"/conversations/{rag.b1}/reset"), headers=w.h["carol"])
    assert reset.status_code == 200
    assert temp_repos() == [] and temp_silo_ids(stack, rag.a2) == []


async def test_a_chat_upload_is_indexed_into_the_conversations_temp_silo(stack, monkeypatch):
    """With the App default embedding service set, an upload is indexed into the conversation's temp silo, created
    with that service; the next turn retrieves the file through the real retriever and does not also get it whole."""
    monkeypatch.setattr("tools.agentTools.get_retriever_tool", REAL_GET_RETRIEVER_TOOL)
    monkeypatch.setattr("tools.vector_stores.pgvector_store.get_embeddings_model", lambda svc: HashEmbeddings())
    w, turns = stack.w, stack.turns
    with Session(stack.engine) as session:
        session.get(App, w.app_id).default_embedding_service_id = w.emb
        session.commit()
    cid = await stack.new_conversation("bob", selection(w.ai["x"]))
    response = await stack.client.post(
        stack.url(f"/conversations/{cid}/files"), headers=w.h["bob"],
        files={"file": (A_FILE, f"{A_MARK} body".encode(), "text/plain")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["vectorized"] is True
    silo_ids = temp_silo_ids(stack, cid)
    assert len(silo_ids) == 1
    assert stack.rows(lambda s: s.get(Silo, silo_ids[0]).embedding_service_id) == w.emb
    turns.retrieve.add("TR")
    result = Result(await stack.send("bob", "TR", selection(w.ai["x"]), cid, message="what is in the file"), "/messages")
    assert result.status == 200
    assert A_MARK in " ".join(r for c in turns.of("TR") for r in c.tool_results), "retrieved through the real retriever"


async def test_without_an_app_default_the_upload_is_not_indexed_as_today(stack):
    w = stack.w
    cid = await stack.new_conversation("bob", selection(w.ai["x"]))
    response = await stack.client.post(
        stack.url(f"/conversations/{cid}/files"), headers=w.h["bob"],
        files={"file": (A_FILE, f"{A_MARK} body".encode(), "text/plain")},
    )
    assert response.status_code == 200 and response.json()["vectorized"] is False
    assert temp_silo_ids(stack, cid) == []


async def test_a_retired_app_default_is_not_used_and_the_upload_still_succeeds(stack, test_engine):
    from datetime import datetime, timedelta, timezone

    w = stack.w
    with Session(test_engine) as session:
        session.get(App, w.app_id).default_embedding_service_id = w.emb
        session.get(EmbeddingService, w.emb).end_of_service_at = datetime.now(timezone.utc) - timedelta(days=1)
        session.commit()
    cid = await stack.new_conversation("bob", selection(w.ai["x"]))
    response = await stack.client.post(
        stack.url(f"/conversations/{cid}/files"), headers=w.h["bob"],
        files={"file": (A_FILE, f"{A_MARK} body".encode(), "text/plain")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["vectorized"] is False
    assert temp_silo_ids(stack, cid) == []
    assert response.json()["file_id"], "the file is kept (it travels in the prompt)"


async def test_changing_the_app_default_keeps_an_existing_temp_silo_on_its_own_service(stack, test_engine, monkeypatch):
    """A temp silo keeps indexing with the service it was created with: no collection ever mixes two models."""
    monkeypatch.setattr("tools.vector_stores.pgvector_store.get_embeddings_model", lambda svc: HashEmbeddings())
    w = stack.w
    with Session(test_engine) as session:
        configure_factories(session)
        second = EmbeddingServiceFactory(app=session.get(App, w.app_id))
        session.get(App, w.app_id).default_embedding_service_id = w.emb
        session.commit()
        second_id = second.service_id
    cid = await stack.new_conversation("bob", selection(w.ai["x"]))

    async def upload(name):
        return await stack.client.post(
            stack.url(f"/conversations/{cid}/files"), headers=w.h["bob"], files={"file": (name, b"some text body", "text/plain")}
        )

    assert (await upload("one.txt")).json()["vectorized"] is True
    silo_id = temp_silo_ids(stack, cid)[0]
    with Session(test_engine) as session:
        session.get(App, w.app_id).default_embedding_service_id = second_id
        session.commit()
    again = await upload("two.txt")
    assert again.status_code == 200 and again.json()["vectorized"] is True
    assert temp_silo_ids(stack, cid) == [silo_id], "still ONE temp silo"
    assert stack.rows(lambda s: s.get(Silo, silo_id).embedding_service_id) == w.emb, "built with the original service"
    # a brand-new conversation uses the new default
    cid2 = await stack.new_conversation("bob", selection(w.ai["x"]))
    other = await stack.client.post(
        stack.url(f"/conversations/{cid2}/files"), headers=w.h["bob"], files={"file": ("three.txt", b"more text", "text/plain")}
    )
    assert other.json()["vectorized"] is True
    assert stack.rows(lambda s: s.get(Silo, temp_silo_ids(stack, cid2)[0]).embedding_service_id) == second_id


# ------------------------------------------------------------------ billing and log hygiene under overlap


async def test_system_model_usage_of_overlapping_turns_is_billed_to_each_sender(stack, test_engine, monkeypatch):
    monkeypatch.setenv("AICT_DEPLOYMENT_MODE", "saas")
    w, turns = stack.w, stack.turns
    with Session(test_engine) as s:
        configure_factories(s)
        system = AIServiceFactory(app=None, name=f"platform-model-{w.tag}", description="gpt-sys")
        s.commit()
        system_id = system.service_id
    w.roots["ai"].add(system_id)  # removed with the rest by ``cworld``
    sel = selection(system_id)
    turns.hold("T1", "T2", "T3")

    async def scenario():
        tasks = [stack.turn("bob", "T1", sel, message="one"), stack.turn("carol", "T2", sel, message="two"),
                 stack.turn("bob", "T3", sel, message="three")]
        await turns.wait_entered("T1", "T2", "T3")
        turns.release("T1", "T2", "T3")
        return [await t for t in tasks]

    results = await stack.run(scenario)
    turns.assert_overlapped("T1", "T2", "T3")
    assert [r.status for r in results] == [200, 200, 200], [r.response.text for r in results]
    users = [w.uid[n] for n in ("alice", "bob", "carol", "dave")]
    records = stack.rows(lambda s: {r.user_id: r.call_count for r in s.query(UsageRecord).filter(UsageRecord.user_id.in_(users))})
    assert records == {w.uid["bob"]: 2, w.uid["carol"]: 1}
    events = [p["event"] for p in await asyncio.to_thread(stack.rec.wait_payloads, 3)]  # not on the loop
    assert sorted((e["user_id"], e["ai_service_id"]) for e in events) == sorted(
        [(w.uid["bob"], system_id)] * 2 + [(w.uid["carol"], system_id)])


async def test_overlapping_turns_log_no_content_token_or_mcp_header(stack, debug_records):
    """Stream + sync + a failing turn that echoes its prompt, all overlapping, with MCP configs holding secrets."""
    w, turns = stack.w, stack.turns
    msgs = {n: f"TOPSECRET-{n}-{uuid.uuid4().hex}" for n in ("bob", "carol", "alice")}
    turns.hold("TA", "TB", "TC")
    turns.fail["TC"] = RuntimeError("provider rejected the request: " + msgs["alice"])

    async def scenario():
        ta = stack.turn("bob", "TA", selection(w.ai["x"], mcps=[w.mcp["m1"]]), path="/stream", message=msgs["bob"])
        tb = stack.turn("carol", "TB", selection(w.ai["y"], mcps=[w.mcp["m1"], w.mcp["m2"]]), message=msgs["carol"])
        tc = stack.turn("alice", "TC", selection(w.ai["x"], mcps=[w.mcp["boom"]]), path="/stream", message=msgs["alice"])
        await turns.wait_entered("TA", "TB", "TC")
        turns.release("TA", "TB", "TC")
        return await ta, await tb, await tc

    a, b, c = await stack.run(scenario)
    turns.assert_overlapped("TA", "TB", "TC")
    assert (a.status, b.status) == (200, 200) and c.failed, "the third turn failed on purpose"
    assert all(m in turns.first(t).everything for m, t in ((msgs["bob"], "TA"), (msgs["carol"], "TB"), (msgs["alice"], "TC"))), (
        "every message did reach its model, so a leak into the logs would be possible")
    needles = {f"message of {n}": m for n, m in msgs.items()}
    for n in ("alice", "bob", "carol"):
        needles[f"jwt of {n}"] = w.jwt[n]
        needles[f"jwt signature of {n}"] = w.jwt[n].rsplit(".", 1)[1]
    needles.update({"mcp secret m1": w.secret["m1"], "mcp secret m2": w.secret["m2"]})
    assert w.secret["m1"] in json.dumps(stack.rec.mcp_clients), "the MCP connections did get their headers"
    assert not [n for n, v in needles.items() if v in a.response.text + b.response.text and n.startswith(("jwt", "mcp"))]

    records = list(debug_records.values())
    assert sum("internal_chat.turn" in r.getMessage() for r in records) == 3, "one turn log line per overlapping turn"
    assert any(r.levelno == logging.DEBUG for r in records)
    formatter = logging.Formatter()
    leaks = []
    for record in records:
        rendered = formatter.format(record) + " " + repr(record.__dict__)
        for label, needle in needles.items():
            if needle in rendered:
                leaks.append((label, record.name, record.levelname, rendered[:200]))
    assert not leaks, leaks
