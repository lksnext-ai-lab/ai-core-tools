"""App Chat code interpreter: the App's default sandbox service drives a per-conversation sandbox.

Everything runs for real (router, ``InternalChatService``, resolver, execution/streaming services, sandbox session
service, skill loader, PostgreSQL) except: the LLM (a scripted fake that issues the tool calls the test asks for) and
the sandbox PROVIDER CLASS (``tools.sandbox.factory._PROVIDER_REGISTRY`` maps every name to an in-memory fake that
records which session key created / ran / destroyed which sandbox). No real sandbox provider is ever called.

``SandboxSessionService`` persists state through ``db.database.SessionLocal()`` (its own connection): it is pointed at
the test transaction so ``Conversation.sandbox_session_id`` / ``sandbox_state`` can be asserted.
"""
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from sqlalchemy.orm import Session

from models.agent import Agent
from models.app import App
from models.conversation import Conversation
from models.internal_chat import ConversationTurn
from models.sandbox_service import SandboxService
from services.sandbox_session_service import sandbox_session_service
from tests.factories import SandboxServiceFactory, SkillFactory, SkillFileFactory
from tests.integration.internal_chat._chat_support import (
    base,
    ok_turn,
    parse_sse,
    selection,
    send,
)
from tests.unit.tools.test_sandbox_ensure_skill_providers import _FakeProviderBase
from tools.sandbox.provider import SandboxHandle

# ------------------------------------------------------------------ fakes


class ChatFakeProvider(_FakeProviderBase):
    """In-memory sandbox provider: one filesystem per sandbox id, every operation recorded at class level.

    ``run_code`` understands ``WRITE <path> <content>`` (writes ``/workspace/<path>``); anything else goes through
    the shell interpreter of the ensure-skill fake (tar extraction, bootstrap, mkdir ...).
    """

    PROVIDER_NAME = "opensandbox"
    SUPPORTED_LANGUAGES = ["python", "bash"]
    STORE: dict[str, dict[str, bytes]] = {}
    SESSION_OF: dict[str, Optional[str]] = {}
    CREATED: list[tuple[Optional[str], str, str]] = []  # (session_key, sandbox_id, working_dir)
    RUNS: list[tuple[Optional[str], str]] = []  # (session_key, code)
    TIMEOUTS: list[tuple[str, Optional[int]]] = []  # (code, timeout) of every run
    DESTROYED: list[str] = []
    INSTANCES: list["ChatFakeProvider"] = []
    LIST_ERROR: Optional[Exception] = None
    BOUNDED_READS: list = []
    EXPIRE_ONCE: bool = False
    ON_RUN = None  # callable run inside run_code for a PROBE command (a tool call of a running turn)
    DESTROY_GATE: Optional[threading.Event] = None
    DESTROY_ERROR: Optional[Exception] = None
    READ_GATE: Optional[threading.Event] = None  # when set, read_file blocks until the event is set

    def __init__(self, credentials=None, **_):
        super().__init__(root="/workspace/.skills")
        self.credentials = credentials
        self._cur = "_none"
        ChatFakeProvider.INSTANCES.append(self)

    @classmethod
    def reset(cls):
        cls.STORE, cls.SESSION_OF = {}, {}
        cls.CREATED, cls.RUNS, cls.DESTROYED, cls.INSTANCES, cls.TIMEOUTS = [], [], [], [], []
        cls.LIST_ERROR, cls.READ_GATE, cls.DESTROY_GATE, cls.DESTROY_ERROR = None, None, None, None
        cls.BOUNDED_READS = []
        cls.EXPIRE_ONCE, cls.ON_RUN = False, None

    @property
    def fs(self):
        return ChatFakeProvider.STORE.setdefault(self._cur, {})

    @fs.setter
    def fs(self, _value):  # the base class assigns its own dict in __init__: ignored
        pass

    def get_supported_languages(self):
        return list(self.SUPPORTED_LANGUAGES)

    def create_sandbox(self, working_dir, *, session_key=None, existing_sandbox_id=None):
        sandbox_id = f"fake-{uuid.uuid4().hex[:8]}"
        ChatFakeProvider.CREATED.append((session_key, sandbox_id, working_dir))
        ChatFakeProvider.SESSION_OF[sandbox_id] = session_key
        ChatFakeProvider.STORE[sandbox_id] = {}
        return SandboxHandle(sandbox_id=sandbox_id, working_dir=working_dir, provider_name="opensandbox",
                             session_key=session_key)

    def destroy_sandbox(self, handle):
        if ChatFakeProvider.DESTROY_GATE is not None:
            ChatFakeProvider.DESTROY_GATE.wait(15)
        if ChatFakeProvider.DESTROY_ERROR is not None:
            raise ChatFakeProvider.DESTROY_ERROR
        ChatFakeProvider.DESTROYED.append(handle.sandbox_id)
        ChatFakeProvider.STORE.pop(handle.sandbox_id, None)

    def destroy_sandbox_id(self, sandbox_id):
        ChatFakeProvider.DESTROYED.append(sandbox_id)
        ChatFakeProvider.STORE.pop(sandbox_id, None)

    def run_code(self, handle, code, **kwargs):
        self._cur = handle.sandbox_id
        ChatFakeProvider.RUNS.append((ChatFakeProvider.SESSION_OF.get(handle.sandbox_id), code))
        ChatFakeProvider.TIMEOUTS.append((code, kwargs.get("timeout")))
        if code == "EXPIRE" and ChatFakeProvider.EXPIRE_ONCE:
            ChatFakeProvider.EXPIRE_ONCE = False
            from tools.sandbox.provider import SandboxExpiredError

            ChatFakeProvider.STORE.pop(handle.sandbox_id, None)
            raise SandboxExpiredError("gone")
        if code == "PROBE" and ChatFakeProvider.ON_RUN is not None:
            ChatFakeProvider.ON_RUN()
            return "probed"
        if code.startswith("BOOM"):
            raise RuntimeError(f"PROVIDER-SECRET-MARKER {code}")
        if code.startswith("WRITE "):
            for line in code.splitlines():
                _, path, content = line.split(" ", 2)
                self.fs[f"/workspace/{path}"] = content.encode()
            return "written"
        if code.startswith("echo "):
            return code[5:]
        return super().run_code(handle, code, **kwargs)

    def write_file(self, handle, filename, content):
        self._cur = handle.sandbox_id
        super().write_file(handle, filename, content)

    def read_file(self, handle, filename):
        self._cur = handle.sandbox_id
        if ChatFakeProvider.READ_GATE is not None:
            ChatFakeProvider.READ_GATE.wait(15)
        for candidate in (filename, f"/workspace/{filename.lstrip('/')}"):
            if candidate in self.fs:
                return self.fs[candidate]
        raise FileNotFoundError(filename)

    def list_files(self, handle):
        self._cur = handle.sandbox_id
        if ChatFakeProvider.LIST_ERROR is not None:
            raise ChatFakeProvider.LIST_ERROR
        return [p for p in self.fs if "/.skills/" not in p]

    def read_file_limited(self, handle, filename, max_bytes):
        data = self.read_file(handle, filename)
        ChatFakeProvider.BOUNDED_READS.append((filename, max_bytes))
        return data[: max_bytes + 1]

    def file_sizes(self, handle, rel_paths):
        self._cur = handle.sandbox_id
        return {r: len(self.fs[f"/workspace/{r}"]) for r in rel_paths if f"/workspace/{r}" in self.fs}


class ScriptedModel(BaseChatModel):
    """Asks for the tool calls scripted in ``rec.plan[service_id]`` (one per model call), then answers."""

    service_id: int
    rec: Any

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.rec.calls.append((self.service_id, [(m.type, m.text) for m in messages]))
        plan = self.rec.plan.get(self.service_id, [])
        if messages[-1].type == "tool" and getattr(self.rec, "between_tools", None) is not None:
            self.rec.between_tools()  # the sandbox is between two tool calls of a running turn
        if self.service_id in getattr(self.rec, "fail_after_tool", set()) and messages[-1].type == "tool":
            raise RuntimeError("model failed after a tool call")
        if plan:
            name, args = plan.pop(0)
            message = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call-{uuid.uuid4().hex[:8]}"}])
        else:
            message = AIMessage(content=f"hello from {self.service_id}")
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, **kwargs):
        names = [getattr(t, "name", None) or t.get("name") or t["function"]["name"] for t in tools]
        self.rec.bound_tools.setdefault(self.service_id, []).append(names)
        return self


@pytest.fixture
def sandbox_env(db, fakes, monkeypatch):
    """Scripted LLM + fake provider registry + test-transaction ``SessionLocal``; sandboxes torn down afterwards."""
    from tools.sandbox import factory

    fakes.plan = {}
    fakes.between_tools = None
    ChatFakeProvider.reset()
    monkeypatch.setattr(
        "tools.aiServiceTools.create_llm_from_service",
        lambda ai_service, temperature=0, is_vision=False: ScriptedModel(service_id=ai_service.service_id, rec=fakes),
    )
    monkeypatch.setattr(factory, "_PROVIDER_REGISTRY", {n: ChatFakeProvider for n in ("opensandbox", "daytona", "e2b")})
    monkeypatch.delenv("SANDBOX_ALLOWED_PROVIDERS", raising=False)
    monkeypatch.setattr("config.SANDBOX_EVICT_MIN_IDLE_S", 0, raising=False)  # tests age nothing; one test sets it
    monkeypatch.setenv("SANDBOX_DEFAULT_PROVIDER", "opensandbox")  # the env fallback the Chat must NEVER use

    def opener():
        return Session(bind=db.get_bind(), join_transaction_mode="create_savepoint", autoflush=False)

    monkeypatch.setattr("db.database.SessionLocal", opener)
    # The singleton's reaper thread would use the SessionLocal pointed at the test connection from another thread.
    monkeypatch.setattr(sandbox_session_service, "_reap_stale", lambda *a, **k: None)
    yield fakes
    for key in list(sandbox_session_service._sessions):
        if key.startswith("conv_"):
            sandbox_session_service.destroy(key)
    sandbox_session_service._sessions.clear()
    sandbox_session_service._creation_locks.clear()
    sandbox_session_service._pending_creates.clear()
    sandbox_session_service._pending_owner.clear()
    ChatFakeProvider.reset()


# ------------------------------------------------------------------ helpers


def enable_switch(db, world, on=True) -> None:
    db.get(App, world["app_id"]).chat_code_interpreter_enabled = on
    db.commit()


def set_default_sandbox(db, world, *, eos=None, provider="opensandbox", switch=True) -> int:
    """An App default sandbox service, with the Chat switch on (the opt-in) unless told otherwise."""
    app = db.get(App, world["app_id"])
    service = SandboxServiceFactory(app=app, provider=provider, end_of_service_at=eos)
    db.flush()
    app.default_sandbox_service_id = service.service_id
    app.chat_code_interpreter_enabled = switch
    db.commit()
    return service.service_id


def options(client, world, who="alice") -> dict:
    response = client.get(base(world["app_id"]) + "/options", headers=world[who])
    assert response.status_code == 200, response.text
    return response.json()


def hidden_agent_id(db, world) -> int:
    return db.query(Agent.agent_id).filter(Agent.app_id == world["app_id"], Agent.kind == "internal_chat").one()[0]


def write_plan(rec, world, path="output/report.txt", content="hello-from-the-sandbox"):
    rec.plan[world["ai_a"]] = [("python_repl", {"code": f"WRITE {path} {content}"})]


def run_turn(client, world, path, message="run it", cid=None, who="alice", sel=None):
    """One turn on ``/messages`` or ``/stream``; returns ``(conversation_id, turn_config summary)``."""
    sel = sel or selection(world["ai_a"])
    if path == "/messages":
        body = ok_turn(client, world, message, sel, cid, who)
        return body["conversation_id"], body["metadata"]["turn_config"]
    response = send(client, world, message, sel, cid, who, path="/stream")
    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    meta = next(e for e in events if e["type"] == "metadata")["data"]
    assert events[-1]["type"] == "done", events[-1]
    return meta["conversation_id"], meta["turn_config"]


def listed_files(client, world, cid, who="alice"):
    return client.get(f"{base(world['app_id'])}/conversations/{cid}/files", headers=world[who])


def conv_row(db, cid) -> Conversation:
    db.expire_all()
    return db.get(Conversation, cid)


# ------------------------------------------------------------------ options


class TestOptions:
    def test_switch_off_is_disabled_whatever_the_default_is(self, client, db, world, sandbox_env):
        assert options(client, world)["code_interpreter"] == {"enabled": False, "reason": "disabled_in_app_settings"}
        set_default_sandbox(db, world, switch=False)  # a default exists, the switch is off
        assert options(client, world)["code_interpreter"] == {"enabled": False, "reason": "disabled_in_app_settings"}

    def test_switch_on_without_default_inherits_the_system_default(self, client, db, world, sandbox_env):
        enable_switch(db, world)
        assert options(client, world)["code_interpreter"] == {"enabled": True, "reason": None}

    def test_system_default_not_registered_or_not_allowed(self, client, db, world, sandbox_env, monkeypatch):
        enable_switch(db, world)
        with patch("tools.sandbox.factory._allowed_providers", return_value=["e2b"]):
            assert options(client, world)["code_interpreter"] == {
                "enabled": False, "reason": "sandbox_provider_unavailable",
            }
        monkeypatch.setenv("SANDBOX_DEFAULT_PROVIDER", "nope")
        assert options(client, world)["code_interpreter"]["reason"] == "sandbox_provider_unavailable"

    def test_active_default(self, client, db, world, sandbox_env):
        set_default_sandbox(db, world)
        assert options(client, world)["code_interpreter"] == {"enabled": True, "reason": None}

    def test_deprecated_default_is_enabled(self, client, db, world, sandbox_env):
        set_default_sandbox(db, world, eos=datetime.now(timezone.utc) + timedelta(days=5))
        assert options(client, world)["code_interpreter"] == {"enabled": True, "reason": None}

    def test_retired_default_does_not_fall_back_to_the_system_default(self, client, db, world, sandbox_env):
        set_default_sandbox(db, world, eos=datetime.now(timezone.utc) - timedelta(days=1))
        assert options(client, world)["code_interpreter"] == {"enabled": False, "reason": "sandbox_service_retired"}

    def test_default_provider_not_allowed_in_the_deployment(self, client, db, world, sandbox_env):
        set_default_sandbox(db, world, provider="daytona")
        with patch("tools.sandbox.factory._allowed_providers", return_value=["e2b"]):
            assert options(client, world)["code_interpreter"] == {
                "enabled": False, "reason": "sandbox_provider_unavailable",
            }

    def test_viewer_sees_it_too(self, client, db, world, sandbox_env):
        set_default_sandbox(db, world)
        assert options(client, world, who="viewer")["code_interpreter"]["enabled"] is True


# ------------------------------------------------------------------ turns


@pytest.mark.parametrize("path", ["/messages", "/stream"])
class TestTurnWithDefaultSandbox:
    def test_tools_are_exposed_and_the_sandbox_is_keyed_by_conversation(self, client, db, world, sandbox_env, path):
        service_id = set_default_sandbox(db, world)
        write_plan(sandbox_env, world)
        cid, summary = run_turn(client, world, path)
        agent_id = hidden_agent_id(db, world)
        key = f"conv_{agent_id}_{cid}"

        assert summary["code_interpreter"] is True
        tools = sandbox_env.tools_of(world["ai_a"], 0)
        assert "python_repl" in tools and "Bash" in tools
        assert "<code_interpreter>" in sandbox_env.system_prompt(world["ai_a"], 0)
        assert [session for session, _, _ in ChatFakeProvider.CREATED] == [key]
        assert [(s, c) for s, c in ChatFakeProvider.RUNS if c.startswith("WRITE")] == [(key, "WRITE output/report.txt hello-from-the-sandbox")]
        # The provider was built from the App's default service credentials, not the env default.
        assert ChatFakeProvider.INSTANCES[0].credentials is not None
        row = conv_row(db, cid)
        assert row.sandbox_session_id == ChatFakeProvider.CREATED[0][1]
        assert f'"sandbox_service_id": {service_id}' in row.sandbox_state
        # The hidden agent stays unconfigured: enablement comes from the turn only.
        assert db.get(Agent, agent_id).enable_code_interpreter is False

    def test_the_output_file_is_listed_and_downloadable_by_its_owner_only(self, client, db, world, sandbox_env, path):
        set_default_sandbox(db, world)
        write_plan(sandbox_env, world)
        cid, _ = run_turn(client, world, path)

        files = listed_files(client, world, cid).json()["files"]
        assert [f["filename"] for f in files] == ["report.txt"]
        download = client.get(f"{base(world['app_id'])}/conversations/{cid}/files/{files[0]['file_id']}/download",
                              headers=world["alice"])
        assert download.status_code == 200, download.text
        # Another member of the App: neither the list nor the download of someone else's conversation.
        assert listed_files(client, world, cid, who="viewer").status_code == 404
        stolen = client.get(f"{base(world['app_id'])}/conversations/{cid}/files/{files[0]['file_id']}/download",
                            headers=world["viewer"])
        assert stolen.status_code == 404

    def test_a_viewer_can_use_the_code_interpreter(self, client, db, world, sandbox_env, path):
        set_default_sandbox(db, world)
        write_plan(sandbox_env, world)
        cid, summary = run_turn(client, world, path, who="viewer")
        assert summary["code_interpreter"] is True
        assert [s for s, _, _ in ChatFakeProvider.CREATED] == [f"conv_{hidden_agent_id(db, world)}_{cid}"]
        assert [f["filename"] for f in listed_files(client, world, cid, who="viewer").json()["files"]] == ["report.txt"]

    def test_switch_on_without_default_uses_the_system_default_like_agents(self, client, db, world, sandbox_env, path):
        enable_switch(db, world)
        write_plan(sandbox_env, world)
        cid, summary = run_turn(client, world, path)
        assert summary["code_interpreter"] is True
        assert "python_repl" in sandbox_env.tools_of(world["ai_a"], 0)
        key = f"conv_{hidden_agent_id(db, world)}_{cid}"
        assert [k for k, _, _ in ChatFakeProvider.CREATED] == [key]
        assert ChatFakeProvider.INSTANCES[0].credentials is None  # env path: no service credentials
        assert '"sandbox_service_id": null' in conv_row(db, cid).sandbox_state

    def test_switch_off_means_no_sandbox_even_with_a_default_and_a_system_default(self, client, db, world, sandbox_env, path):
        set_default_sandbox(db, world, switch=False)
        write_plan(sandbox_env, world)
        _, summary = run_turn(client, world, path)
        assert summary["code_interpreter"] is False
        assert not {"python_repl", "Bash", "load_skill"} & set(sandbox_env.tools_of(world["ai_a"], 0))
        assert "<code_interpreter>" not in sandbox_env.system_prompt(world["ai_a"], 0)
        assert ChatFakeProvider.CREATED == [] and ChatFakeProvider.INSTANCES == []

    def test_an_app_never_opted_in_has_no_sandbox(self, client, db, world, sandbox_env, path):
        write_plan(sandbox_env, world)
        cid, summary = run_turn(client, world, path)
        assert summary["code_interpreter"] is False
        assert "python_repl" not in sandbox_env.tools_of(world["ai_a"], 0)
        assert ChatFakeProvider.CREATED == [] and conv_row(db, cid).sandbox_session_id is None

    def test_a_deprecated_default_works_on_a_real_turn(self, client, db, world, sandbox_env, path):
        set_default_sandbox(db, world, eos=datetime.now(timezone.utc) + timedelta(days=5))
        write_plan(sandbox_env, world)
        _, summary = run_turn(client, world, path)
        assert summary["code_interpreter"] is True and len(ChatFakeProvider.CREATED) == 1

    def test_a_provider_that_became_unavailable_after_the_resolve_degrades_the_turn(
        self, client, db, world, sandbox_env, path
    ):
        from tools.sandbox.factory import SandboxProviderUnavailableError

        set_default_sandbox(db, world, provider="daytona")
        write_plan(sandbox_env, world)
        with patch("tools.sandbox.factory.provider_for_service", side_effect=SandboxProviderUnavailableError("gone")):
            cid, summary = run_turn(client, world, path)
        assert "python_repl" not in sandbox_env.tools_of(world["ai_a"], 0)
        assert ChatFakeProvider.CREATED == [] and ChatFakeProvider.INSTANCES == []
        # /messages reads the summary after the run (false); /stream emits it before (the degrade is already known
        # at prepare, which runs before the metadata event).
        assert summary["code_interpreter"] is False

    def test_a_sandbox_that_cannot_be_created_degrades_quietly_and_the_turn_succeeds(
        self, client, db, world, sandbox_env, path, monkeypatch
    ):
        """The sandbox host is down: options say enabled, the first tool call cannot create it."""
        enable_switch(db, world)

        def refuse(self, working_dir, *, session_key=None, existing_sandbox_id=None):
            raise ConnectionError("SECRET-MARKER connection refused")

        monkeypatch.setattr(ChatFakeProvider, "create_sandbox", refuse)
        assert options(client, world)["code_interpreter"]["enabled"] is True
        write_plan(sandbox_env, world)
        cid, summary = run_turn(client, world, path)
        messages = client.get(f"{base(world['app_id'])}/conversations/{cid}", headers=world["alice"]).json()["messages"]
        assert [m["role"] for m in messages] == ["user", "agent"]
        assert listed_files(client, world, cid).json()["files"] == []
        if path == "/messages":  # the summary of /stream is emitted before the tool call that fails
            assert summary["code_interpreter"] is False

    def test_a_retired_default_runs_the_turn_without_code_interpreter(self, client, db, world, sandbox_env, path):
        set_default_sandbox(db, world, eos=datetime.now(timezone.utc) - timedelta(days=1))
        write_plan(sandbox_env, world)
        _, summary = run_turn(client, world, path)
        assert summary["code_interpreter"] is False
        assert "python_repl" not in sandbox_env.tools_of(world["ai_a"], 0)
        assert ChatFakeProvider.CREATED == [] and ChatFakeProvider.INSTANCES == []

    def test_a_selected_skill_is_materialised_in_that_conversations_sandbox(self, client, db, world, sandbox_env, path):
        set_default_sandbox(db, world)
        app = db.get(App, world["app_id"])
        skill = SkillFactory(app=app, name="chat-sbx-skill", content="# Use scripts/run.py")
        SkillFileFactory(skill=skill, path="scripts/run.py", content_text="print('hi')", media_type="text/x-python")
        db.commit()
        sandbox_env.plan[world["ai_a"]] = [("load_skill", {"skill_name": "chat-sbx-skill"})]
        cid, _ = run_turn(client, world, path, sel=selection(world["ai_a"], skills=[skill.skill_id]))

        assert "load_skill" in sandbox_env.tools_of(world["ai_a"], 0)
        assert len(ChatFakeProvider.CREATED) == 1
        key, sandbox_id, _ = ChatFakeProvider.CREATED[0]
        assert key == f"conv_{hidden_agent_id(db, world)}_{cid}"
        assert ChatFakeProvider.STORE[sandbox_id]["/workspace/.skills/chat-sbx-skill/scripts/run.py"] == b"print('hi')"

    def test_delete_destroys_the_sandbox_and_clears_its_state(self, client, db, world, sandbox_env, path):
        set_default_sandbox(db, world)
        write_plan(sandbox_env, world)
        cid, _ = run_turn(client, world, path)
        sandbox_id = ChatFakeProvider.CREATED[0][1]
        assert conv_row(db, cid).sandbox_session_id == sandbox_id

        response = client.delete(f"{base(world['app_id'])}/conversations/{cid}", headers=world["alice"])
        assert response.status_code in (200, 204), response.text
        assert ChatFakeProvider.DESTROYED == [sandbox_id]
        assert not any(k.endswith(f"_{cid}") for k in sandbox_session_service._sessions)

    def test_reset_destroys_the_sandbox_and_clears_its_state(self, client, db, world, sandbox_env, path):
        set_default_sandbox(db, world)
        write_plan(sandbox_env, world)
        cid, _ = run_turn(client, world, path)
        sandbox_id = ChatFakeProvider.CREATED[0][1]

        response = client.post(f"{base(world['app_id'])}/conversations/{cid}/reset", headers=world["alice"])
        assert response.status_code == 200, response.text
        assert ChatFakeProvider.DESTROYED == [sandbox_id]
        row = conv_row(db, cid)
        assert row.sandbox_session_id is None and row.sandbox_state is None
        assert not any(k.endswith(f"_{cid}") for k in sandbox_session_service._sessions)

        # After the reset the conversation gets a brand-new sandbox, still keyed by the same conversation.
        write_plan(sandbox_env, world, content="again")
        run_turn(client, world, path, cid=cid)
        assert len(ChatFakeProvider.CREATED) == 2
        assert ChatFakeProvider.CREATED[1][0] == ChatFakeProvider.CREATED[0][0]
        assert ChatFakeProvider.CREATED[1][1] != sandbox_id


# ------------------------------------------------------------------ isolation


class TestIsolation:
    def test_two_users_of_the_same_app_never_share_a_sandbox_or_files(self, client, db, world, sandbox_env):
        set_default_sandbox(db, world)
        write_plan(sandbox_env, world, "output/alice.txt", "alice-secret")
        alice_cid, _ = run_turn(client, world, "/messages", who="alice")
        write_plan(sandbox_env, world, "output/viewer.txt", "viewer-secret")
        viewer_cid, _ = run_turn(client, world, "/stream", who="viewer")
        agent_id = hidden_agent_id(db, world)  # the SAME hidden agent for both users

        assert alice_cid != viewer_cid
        keys = [k for k, _, _ in ChatFakeProvider.CREATED]
        assert keys == [f"conv_{agent_id}_{alice_cid}", f"conv_{agent_id}_{viewer_cid}"]
        (_, alice_box, alice_dir), (_, viewer_box, viewer_dir) = ChatFakeProvider.CREATED
        assert alice_box != viewer_box and alice_dir != viewer_dir
        assert alice_dir.endswith(str(alice_cid)) and viewer_dir.endswith(str(viewer_cid))
        # Each sandbox only ever saw its own writes (and its own skill markers).
        assert ChatFakeProvider.STORE[alice_box]["/workspace/output/alice.txt"] == b"alice-secret"
        assert "/workspace/output/viewer.txt" not in ChatFakeProvider.STORE[alice_box]
        assert "/workspace/output/alice.txt" not in ChatFakeProvider.STORE[viewer_box]
        for session, code in ChatFakeProvider.RUNS:
            if code.startswith("WRITE "):
                assert (session, "alice" in code) in {(keys[0], True), (keys[1], False)}
        # Persisted state of each conversation points at its own sandbox only.
        assert conv_row(db, alice_cid).sandbox_session_id == alice_box
        assert conv_row(db, viewer_cid).sandbox_session_id == viewer_box
        # Output files: each owner sees only its own; the other conversation is a 404.
        assert [f["filename"] for f in listed_files(client, world, alice_cid).json()["files"]] == ["alice.txt"]
        assert [f["filename"] for f in listed_files(client, world, viewer_cid, who="viewer").json()["files"]] == ["viewer.txt"]
        assert listed_files(client, world, alice_cid, who="viewer").status_code == 404
        assert listed_files(client, world, viewer_cid, who="alice").status_code == 404

    def test_a_second_turn_of_a_conversation_reuses_its_sandbox(self, client, db, world, sandbox_env):
        set_default_sandbox(db, world)
        write_plan(sandbox_env, world, "output/one.txt", "1")
        cid, _ = run_turn(client, world, "/messages")
        write_plan(sandbox_env, world, "output/two.txt", "2")
        run_turn(client, world, "/stream", cid=cid)
        assert len(ChatFakeProvider.CREATED) == 1
        assert {s for s, c in ChatFakeProvider.RUNS if c.startswith("WRITE")} == {ChatFakeProvider.CREATED[0][0]}
        assert sorted(f["filename"] for f in listed_files(client, world, cid).json()["files"]) == ["one.txt", "two.txt"]

    def test_deleting_one_conversation_leaves_the_other_users_sandbox_alone(self, client, db, world, sandbox_env):
        set_default_sandbox(db, world)
        write_plan(sandbox_env, world, "output/a.txt", "a")
        alice_cid, _ = run_turn(client, world, "/messages", who="alice")
        write_plan(sandbox_env, world, "output/v.txt", "v")
        viewer_cid, _ = run_turn(client, world, "/messages", who="viewer")
        alice_box, viewer_box = ChatFakeProvider.CREATED[0][1], ChatFakeProvider.CREATED[1][1]

        assert client.delete(f"{base(world['app_id'])}/conversations/{alice_cid}", headers=world["alice"]).status_code in (200, 204)
        assert ChatFakeProvider.DESTROYED == [alice_box]
        assert conv_row(db, viewer_cid).sandbox_session_id == viewer_box
        assert viewer_box in ChatFakeProvider.STORE

    def test_a_chat_turn_never_reaches_a_thread_or_anon_key(self, client, db, world, sandbox_env):
        set_default_sandbox(db, world)
        write_plan(sandbox_env, world)
        run_turn(client, world, "/messages")
        assert all(k.startswith("conv_") for k in (c[0] for c in ChatFakeProvider.CREATED))
        assert all(s is None or s.startswith("conv_") for s, _ in ChatFakeProvider.RUNS)
        assert not any(k.startswith(("thread_", "anon_")) for k in sandbox_session_service._sessions)


# ------------------------------------------------------------------ bounded output delivery (both routes)


def _drain_pull_pool() -> None:
    """Let the hung pull worker finish: in production it has its own DB connection, here it shares the test one."""
    import services.sandbox_output_pull as module

    pool, module._pool = module._pool, None
    module._slots = None
    if pool is not None:
        pool.shutdown(wait=True)


def _turn_rows(db, cid) -> int:
    db.expire_all()
    return db.query(ConversationTurn).filter_by(conversation_id=cid).count()


def _answer_roles(client, world, cid):
    return [m["role"] for m in client.get(
        f"{base(world['app_id'])}/conversations/{cid}", headers=world["alice"]).json()["messages"]]


@pytest.mark.parametrize("path", ["/messages", "/stream"])
class TestOutputDelivery:
    def test_a_failing_listing_keeps_the_answer_and_the_turn_row(self, client, db, world, sandbox_env, path):
        set_default_sandbox(db, world)
        write_plan(sandbox_env, world)
        ChatFakeProvider.LIST_ERROR = RuntimeError("listing exploded")
        cid, _ = run_turn(client, world, path)
        assert _answer_roles(client, world, cid) == ["user", "agent"]
        assert _turn_rows(db, cid) == 1
        assert listed_files(client, world, cid).json()["files"] == []
        # busy marker released: the next turn is accepted
        ChatFakeProvider.LIST_ERROR = None
        write_plan(sandbox_env, world, "output/after.txt", "ok")
        run_turn(client, world, path, cid=cid)
        assert [f["filename"] for f in listed_files(client, world, cid).json()["files"]] == ["after.txt"]

    def test_a_read_that_hangs_past_the_budget_never_fails_the_answer(self, client, db, world, sandbox_env, path, monkeypatch):
        monkeypatch.setattr("config.SANDBOX_PULL_TIME_BUDGET_S", 0.5, raising=False)
        set_default_sandbox(db, world)
        write_plan(sandbox_env, world)
        gate = ChatFakeProvider.READ_GATE = threading.Event()
        try:
            cid, _ = run_turn(client, world, path)
        finally:
            gate.set()
            _drain_pull_pool()
        assert _answer_roles(client, world, cid) == ["user", "agent"]
        assert _turn_rows(db, cid) == 1
        assert listed_files(client, world, cid).json()["files"] == []
        ChatFakeProvider.READ_GATE = None
        run_turn(client, world, path, cid=cid)  # the marker was released: no 409

    def test_oversized_files_are_skipped_with_a_content_free_warning(self, client, db, world, sandbox_env, path, monkeypatch):
        monkeypatch.setattr("config.SANDBOX_PULL_MAX_FILE_BYTES", 5, raising=False)
        set_default_sandbox(db, world)
        sandbox_env.plan[world["ai_a"]] = [(
            "python_repl", {"code": "WRITE output/small.txt hi\nWRITE output/big.txt 0123456789"},
        )]
        if path == "/messages":
            body = ok_turn(client, world, "go", selection(world["ai_a"]))
            cid = body["conversation_id"]
            assert {"kind": "sandbox_output", "id": 1} in body["turn"]["warnings"]
        else:
            cid, _ = run_turn(client, world, path)
        assert [f["filename"] for f in listed_files(client, world, cid).json()["files"]] == ["small.txt"]

    def test_two_remote_files_with_the_same_name_do_not_overwrite_each_other(self, client, db, world, sandbox_env, path):
        set_default_sandbox(db, world)
        sandbox_env.plan[world["ai_a"]] = [(
            "python_repl", {"code": "WRITE output/a/x.txt one\nWRITE output/b/x.txt two"},
        )]
        cid, _ = run_turn(client, world, path)
        assert sorted(f["filename"] for f in listed_files(client, world, cid).json()["files"]) == ["x-2.txt", "x.txt"]
        # every pulled file went through the BOUNDED read, never the unbounded one
        assert len(ChatFakeProvider.BOUNDED_READS) == 2
        assert all(cap == 50 * 1024 * 1024 for _, cap in ChatFakeProvider.BOUNDED_READS)


# ------------------------------------------------------------------ per-turn execution limits


class TestChatExecutionLimits:
    def test_repl_and_bash_share_one_budget_and_bash_is_capped_without_background(
        self, client, db, world, sandbox_env, monkeypatch
    ):
        monkeypatch.setattr("config.SANDBOX_MAX_EXECUTIONS_PER_TURN", 2, raising=False)
        monkeypatch.setattr("config.SANDBOX_CHAT_BASH_MAX_TIMEOUT_S", 7, raising=False)
        set_default_sandbox(db, world)
        sandbox_env.plan[world["ai_a"]] = [
            ("python_repl", {"code": "WRITE output/a.txt 1"}),
            ("Bash", {"command": "echo B", "timeout": 900000}),
            ("Bash", {"command": "echo NOHUP-BG", "run_in_background": True}),
            ("python_repl", {"code": "WRITE output/c.txt 3"}),
        ]
        run_turn(client, world, "/messages")
        user_runs = [c for _, c in ChatFakeProvider.RUNS if c.startswith(("WRITE", "echo"))]
        assert user_runs == ["WRITE output/a.txt 1", "echo B"]  # the third and fourth were refused
        assert [t for c, t in ChatFakeProvider.TIMEOUTS if c == "echo B"] == [7]
        assert not any("NOHUP-BG" in c or "nohup" in c for _, c in ChatFakeProvider.RUNS)
        last_call = sandbox_env.calls_of(world["ai_a"])[-1]
        assert any("Execution budget exceeded" in text for kind, text in last_call if kind == "tool")


# ------------------------------------------------------------------ logging rule


class TestChatLogsNeverCarryProviderText:
    def test_a_provider_error_and_a_file_name_never_reach_the_logs(self, client, db, world, sandbox_env, debug_records):
        import traceback

        set_default_sandbox(db, world)
        ChatFakeProvider.LIST_ERROR = RuntimeError("PROVIDER-SECRET-MARKER output/MARKER-FILE.txt")
        sandbox_env.plan[world["ai_a"]] = [
            ("python_repl", {"code": "BOOM output/MARKER-FILE.txt"}),
            ("python_repl", {"code": "WRITE output/MARKER-FILE.txt x"}),
        ]
        run_turn(client, world, "/messages")
        offenders = []
        for record in list(debug_records.values()):
            text = record.getMessage()
            if record.exc_info:
                text += "".join(traceback.format_exception_only(*record.exc_info[:2]))
            if "PROVIDER-SECRET-MARKER" in text or "MARKER-FILE" in text:
                offenders.append((record.name, text[:120]))
        assert offenders == []


# ------------------------------------------------------------------ lifecycle edge cases


class TestLifecycle:
    def test_a_busy_conversation_gets_409_and_no_sandbox_is_created_or_destroyed(self, client, db, world, sandbox_env):
        import uuid as _uuid

        from repositories.internal_chat_repository import ChatConversationStateRepository

        set_default_sandbox(db, world)
        cid, _ = run_turn(client, world, "/messages")  # no tool call: no sandbox yet
        assert ChatConversationStateRepository.claim_busy(db, cid, _uuid.uuid4(), 600)
        db.commit()
        write_plan(sandbox_env, world)
        built_before = len(ChatFakeProvider.INSTANCES)
        response = send(client, world, "again", selection(world["ai_a"]), cid)
        assert response.status_code == 409 and response.json()["error_code"] == "CONVERSATION_BUSY"
        assert ChatFakeProvider.CREATED == [] and ChatFakeProvider.DESTROYED == []
        assert len(ChatFakeProvider.INSTANCES) == built_before  # the refused turn did not even build a provider

    def test_a_slow_or_failing_provider_destroy_does_not_stall_or_fail_delete_and_reset(
        self, client, db, world, sandbox_env, monkeypatch
    ):
        import time

        monkeypatch.setattr("services.internal_chat.chat_service.SANDBOX_DESTROY_TIMEOUT_S", 0.3)
        set_default_sandbox(db, world)
        write_plan(sandbox_env, world)
        cid, _ = run_turn(client, world, "/messages")
        gate = ChatFakeProvider.DESTROY_GATE = threading.Event()
        try:
            started = time.monotonic()
            response = client.post(f"{base(world['app_id'])}/conversations/{cid}/reset", headers=world["alice"])
            assert response.status_code == 200, response.text
            assert time.monotonic() - started < 8
            # the destroy was NOT confirmed: the persisted state stays so the DB reaper can still find the sandbox
            assert conv_row(db, cid).sandbox_session_id is not None
        finally:
            gate.set()
        ChatFakeProvider.DESTROY_GATE = None
        write_plan(sandbox_env, world)
        run_turn(client, world, "/messages", cid=cid)
        ChatFakeProvider.DESTROY_ERROR = RuntimeError("destroy failed")
        response = client.delete(f"{base(world['app_id'])}/conversations/{cid}", headers=world["alice"])
        assert response.status_code in (200, 204), response.text

    def test_deleting_a_user_destroys_that_users_chat_sandboxes(self, client, db, world, sandbox_env):
        from services.internal_chat.user_cleanup import finish_user_chat_conversations, stage_user_chat_conversations

        set_default_sandbox(db, world)
        write_plan(sandbox_env, world, "output/a.txt", "a")
        run_turn(client, world, "/messages", who="alice")
        write_plan(sandbox_env, world, "output/v.txt", "v")
        run_turn(client, world, "/messages", who="viewer")
        alice_box = ChatFakeProvider.CREATED[0][1]
        staged = stage_user_chat_conversations(db, world["alice_id"])
        assert len(staged) == 1
        finish_user_chat_conversations(db, world["alice_id"], staged)
        assert ChatFakeProvider.DESTROYED == [alice_box]  # the viewer's sandbox is untouched


class TestSessionLimits:
    def test_a_users_third_conversation_evicts_their_lru_one_and_the_evicted_one_gets_a_fresh_sandbox(
        self, client, db, world, sandbox_env, monkeypatch
    ):
        monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_USER", 2, raising=False)
        set_default_sandbox(db, world)
        write_plan(sandbox_env, world, "output/v.txt", "v")
        viewer_cid, _ = run_turn(client, world, "/messages", who="viewer")
        cids = []
        for i in range(3):
            write_plan(sandbox_env, world, f"output/a{i}.txt", str(i))
            cid, _ = run_turn(client, world, "/messages", who="alice")
            cids.append(cid)
        boxes = {ChatFakeProvider.SESSION_OF[b]: b for _, b, _ in ChatFakeProvider.CREATED}
        agent_id = hidden_agent_id(db, world)
        assert ChatFakeProvider.DESTROYED == [boxes[f"conv_{agent_id}_{cids[0]}"]]  # alice's LRU, nobody else's
        assert conv_row(db, cids[0]).sandbox_session_id is None
        assert conv_row(db, viewer_cid).sandbox_session_id == boxes[f"conv_{agent_id}_{viewer_cid}"]
        # the evicted conversation transparently gets a fresh sandbox (and in turn evicts alice's next LRU)
        write_plan(sandbox_env, world, "output/again.txt", "x")
        run_turn(client, world, "/messages", cid=cids[0], who="alice")
        assert [k for k, _, _ in ChatFakeProvider.CREATED].count(f"conv_{agent_id}_{cids[0]}") == 2


# ------------------------------------------------------------------ lease, eviction policy, recovery


def _entry(key):
    return sandbox_session_service._sessions.get(key)


class TestTurnLeaseAndEvictionPolicy:
    def test_a_running_turns_sandbox_is_never_evicted_by_its_user_or_by_another_user(
        self, client, db, world, sandbox_env, monkeypatch
    ):
        monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_USER", 1, raising=False)
        monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_APP", 0, raising=False)
        set_default_sandbox(db, world)
        outcomes = []

        def probe():
            from services.sandbox_session_service import SandboxCapacityError

            key = next(k for k in sandbox_session_service._sessions if k.startswith("conv_"))
            running = sandbox_session_service._sessions[key]
            outcomes.append(("lease", running.active_uses))  # only the turn lease: no tool call is running now
            prov = ChatFakeProvider()
            try:  # the SAME user opens another conversation mid-turn (user limit 1)
                sandbox_session_service.get_or_create(
                    "conv_9999_1", prov, "/tmp", owner=(world["app_id"], world["alice_id"]))
                outcomes.append(("same-user", "created"))
            except SandboxCapacityError:
                outcomes.append(("same-user", "refused"))
            monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_USER", 0, raising=False)
            monkeypatch.setattr("config.SANDBOX_MAX_SESSIONS_PER_APP", 1, raising=False)
            try:  # ANOTHER user fills the App limit: alice's session is not theirs to evict
                sandbox_session_service.get_or_create(
                    "conv_9999_2", prov, "/tmp", owner=(world["app_id"], world["alice_id"] + 12345))
                outcomes.append(("other-user", "created"))
            except SandboxCapacityError:
                outcomes.append(("other-user", "refused"))
            outcomes.append(("alive", key in sandbox_session_service._sessions))

        sandbox_env.between_tools = probe  # runs between the tool call and the next model call (no tool is running)
        sandbox_env.plan[world["ai_a"]] = [("python_repl", {"code": "WRITE output/a.txt 1"})]
        cid, _ = run_turn(client, world, "/messages")
        assert [o if o[0] != "lease" else ("lease", o[1]) for o in outcomes] == [("lease", 1), ("same-user", "refused"), ("other-user", "refused"), ("alive", True)]
        assert ChatFakeProvider.DESTROYED == []
        # after the turn: lease released, the reaper can collect the now idle session
        key = f"conv_{hidden_agent_id(db, world)}_{cid}"
        assert _entry(key).active_uses == 0

    @pytest.mark.parametrize("failure", ["tool_error", "model_error"])
    def test_the_lease_is_released_after_a_failed_turn(self, client, db, world, sandbox_env, failure):
        set_default_sandbox(db, world)
        first_cid, _ = run_turn(client, world, "/messages")  # the conversation survives a later failing turn
        if failure == "tool_error":
            sandbox_env.plan[world["ai_a"]] = [("python_repl", {"code": "BOOM x"})]
            run_turn(client, world, "/messages", cid=first_cid)
        else:
            sandbox_env.plan[world["ai_a"]] = [("python_repl", {"code": "WRITE output/a.txt 1"})]
            sandbox_env.fail_after_tool = {world["ai_a"]}
            response = send(client, world, "go", selection(world["ai_a"]), first_cid)
            assert response.status_code >= 400
        entries = [e for k, e in sandbox_session_service._sessions.items() if k.startswith("conv_")]
        assert entries and all(e.active_uses == 0 for e in entries)
        assert entries[0].lease_expires_at is None  # nothing pins it: the reaper (neutralised here) could collect it


class TestMidTurnRecovery:
    @pytest.mark.parametrize("path", ["/messages", "/stream"])
    def test_a_sandbox_lost_mid_turn_is_recreated_with_owner_state_and_outputs_are_delivered(
        self, client, db, world, sandbox_env, path
    ):
        set_default_sandbox(db, world)
        ChatFakeProvider.EXPIRE_ONCE = True
        sandbox_env.plan[world["ai_a"]] = [
            ("python_repl", {"code": "WRITE output/a.txt 1"}),
            ("python_repl", {"code": "EXPIRE"}),
            ("python_repl", {"code": "WRITE output/b.txt 2"}),
        ]
        cid, _ = run_turn(client, world, path)
        key = f"conv_{hidden_agent_id(db, world)}_{cid}"
        assert [k for k, _, _ in ChatFakeProvider.CREATED] == [key, key]
        new_box = ChatFakeProvider.CREATED[1][1]
        entry = _entry(key)
        assert entry.owner == (world["app_id"], world["alice_id"]) and entry.handle.sandbox_id == new_box
        assert conv_row(db, cid).sandbox_session_id == new_box  # persisted for the NEW sandbox
        assert entry.active_uses == 0  # the new sandbox held the lease and it was released
        # the output pull used the new handle: b.txt (written after the recovery) is delivered
        assert "b.txt" in [f["filename"] for f in listed_files(client, world, cid).json()["files"]]
