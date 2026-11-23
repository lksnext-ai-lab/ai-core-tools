"""A Chat turn that runs out of graph steps keeps the conversation, its checkpoint and its sandbox (the user can continue)."""
import pytest

from models.conversation import Conversation
from models.internal_chat import ConversationTurn
from services.sandbox_session_service import sandbox_session_service
from tests.integration.internal_chat._chat_support import base, parse_sse, selection, send
from tests.integration.internal_chat.test_chat_code_interpreter import (  # noqa: F401  (fixtures + helpers)
    ChatFakeProvider,
    conv_row,
    hidden_agent_id,
    listed_files,
    options,
    run_turn,
    sandbox_env,
    set_default_sandbox,
)

CODE = "STEP_LIMIT_REACHED"


def many_calls(rec, world, n=60):
    rec.plan[world["ai_a"]] = [("python_repl", {"code": "WRITE output/early.txt written-before-the-limit"})] + [
        ("python_repl", {"code": "echo OUT-MARKER-1"}) for _ in range(n)
    ]


def conversations(client, world):
    body = client.get(f"{base(world['app_id'])}/conversations", headers=world["alice"]).json()
    return [c["conversation_id"] for c in body["conversations"]]


def turn_rows(db, cid):
    db.expire_all()
    return db.query(ConversationTurn).filter_by(conversation_id=cid).count()


@pytest.mark.parametrize("path", ["/messages", "/stream"])
def test_step_limit_keeps_the_conversation_and_the_next_turn_continues(client, db, world, sandbox_env, path, monkeypatch):
    monkeypatch.setattr("tools.agentTools.AICT_CHAT_RECURSION_LIMIT", 8)
    set_default_sandbox(db, world)
    many_calls(sandbox_env, world)
    response = send(client, world, "do a lot", selection(world["ai_a"]), path=path)
    if path == "/messages":
        assert response.status_code == 422, response.text
        body = response.json()
        assert body["error_code"] == CODE and "step limit" in body["detail"]
        assert "OUT-MARKER" not in response.text
    else:
        assert response.status_code == 200
        events = parse_sse(response.text)
        error = next(e for e in events if e["type"] == "error")
        assert error["data"]["code"] == "step_limit_reached" and "OUT-MARKER" not in str(error)
        assert not any(e["type"] == "done" for e in events)

    # kept: the conversation is listed, its sandbox lives, no turn row was written, the marker is free
    cids = conversations(client, world)
    assert len(cids) == 1
    cid = cids[0]
    assert ChatFakeProvider.CREATED and ChatFakeProvider.DESTROYED == []
    assert turn_rows(db, cid) == 0
    key = f"conv_{hidden_agent_id(db, world)}_{cid}"
    assert key in sandbox_session_service._sessions and sandbox_session_service._sessions[key].active_uses == 0
    # the file written before the limit was saved by the failed turn itself
    assert [f["filename"] for f in listed_files(client, world, cid).json()["files"]] == ["early.txt"]

    # the user continues in the same conversation on the same checkpoint
    sandbox_env.plan[world["ai_a"]] = []
    follow_up = send(client, world, "continue", selection(world["ai_a"]), cid, path=path)
    assert follow_up.status_code == 200, follow_up.text
    if path == "/stream":
        assert parse_sse(follow_up.text)[-1]["type"] == "done"
    assert turn_rows(db, cid) == 1
    assert conversations(client, world) == [cid]
    assert [f["filename"] for f in listed_files(client, world, cid).json()["files"]] == ["early.txt"]
    assert len(ChatFakeProvider.CREATED) == 1  # same sandbox, nothing destroyed in between


def test_the_agent_limit_is_not_used_by_the_chat(client, db, world, sandbox_env, monkeypatch):
    monkeypatch.setattr("tools.agentTools.AICT_AGENT_RECURSION_LIMIT", 3)  # would stop a chat turn at once
    monkeypatch.setattr("tools.agentTools.AICT_CHAT_RECURSION_LIMIT", 100)
    set_default_sandbox(db, world)
    sandbox_env.plan[world["ai_a"]] = [("python_repl", {"code": "echo hi"}) for _ in range(4)]
    response = send(client, world, "go", selection(world["ai_a"]))
    assert response.status_code == 200, response.text


def test_tool_calls_are_logged_by_name_and_outcome_only(client, db, world, sandbox_env, debug_records, monkeypatch):
    monkeypatch.setattr("tools.agentTools.AICT_CHAT_RECURSION_LIMIT", 8)
    set_default_sandbox(db, world)
    sandbox_env.plan[world["ai_a"]] = [("python_repl", {"code": "echo OUT-MARKER-2"})] + [
        ("python_repl", {"code": "BOOM ARG-MARKER-2"}) for _ in range(40)
    ]
    send(client, world, "SECRET-MESSAGE-MARKER", selection(world["ai_a"]))
    lines = [r.getMessage() for r in debug_records.values()]
    tool_lines = [m for m in lines if m.startswith("chat tool=")]
    assert tool_lines and all("tool=python_repl" in m and " n=" in m and " ms=" in m for m in tool_lines)
    assert any("outcome=ok" in m for m in tool_lines)
    summary = [m for m in lines if "reached the step limit" in m]
    assert summary and "model_calls=" in summary[0] and "python_repl" in summary[0]
    leaked = [m for m in lines if any(k in m for k in ("OUT-MARKER-2", "ARG-MARKER-2", "SECRET-MESSAGE-MARKER"))]
    assert leaked == []


# ------------------------------------------------------------------ where the checkpoint ends, and the next turn

import os
import uuid
from collections import Counter

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ModeModel(BaseChatModel):
    """``loop``: every call asks for 2 PARALLEL tool calls in one AIMessage. ``strict``: validates the history it is
    handed (every tool_call answered exactly once, no tool ran since the turn started) and answers in plain text."""

    service_id: int
    rec: object

    @property
    def _llm_type(self) -> str:
        return "mode-model"

    def bind_tools(self, tools, **kwargs):
        self.rec.bound_tools.setdefault(self.service_id, []).append([getattr(t, "name", "?") for t in tools])
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.rec.mode == "loop":
            calls = [{"name": "python_repl", "args": {"code": f"echo {tag}"}, "id": f"call-{uuid.uuid4().hex[:10]}"}
                     for tag in ("A", "B")]
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=calls))])
        asked = [c["id"] for m in messages if isinstance(m, AIMessage) for c in (m.tool_calls or [])]
        answered = Counter(m.tool_call_id for m in messages if isinstance(m, ToolMessage))
        self.rec.report = {
            "asked": asked,
            "answered_once": all(answered[i] == 1 for i in asked) and set(answered) <= set(asked),
            "runs_at_model_call": sum(1 for _, c in ChatFakeProvider.RUNS if c.startswith("echo")),
        }
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="continued"))])


def thread_state(thread_id):
    """What the checkpointer holds for the thread right now: kind of the last message + pending writes."""
    import asyncio

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    uri = os.environ["SQLALCHEMY_DATABASE_URI"].replace("+psycopg2", "")

    async def read():
        async with AsyncPostgresSaver.from_conn_string(uri) as saver:
            return await saver.aget_tuple({"configurable": {"thread_id": thread_id}})

    loop = asyncio.new_event_loop()
    try:
        tup = loop.run_until_complete(read())
    finally:
        loop.close()
    messages = tup.checkpoint["channel_values"].get("messages", []) if tup else []
    last = messages[-1] if messages else None
    return {
        "last": type(last).__name__,
        "last_tool_calls": len(getattr(last, "tool_calls", None) or []),
        "pending_writes": len(tup.pending_writes or []) if tup else 0,
        "step": tup.metadata.get("step") if tup else None,
    }


@pytest.mark.parametrize("limit", [5, 6, 7, 8, 9])
def test_the_checkpoint_after_the_limit_is_continuable_whichever_step_it_was_cut_at(
    client, db, world, sandbox_env, monkeypatch, limit
):
    monkeypatch.setattr("tools.agentTools.AICT_CHAT_RECURSION_LIMIT", limit)
    monkeypatch.setattr(
        "tools.aiServiceTools.create_llm_from_service",
        lambda ai_service, temperature=0, is_vision=False: ModeModel(service_id=ai_service.service_id, rec=sandbox_env),
    )
    # Two parallel tool threads would persist the sandbox state at the same moment through the ONE shared test
    # connection (a harness artifact, production uses separate connections): state persistence is not under test here.
    monkeypatch.setattr("services.sandbox_session_service._persist_sandbox_state", lambda *a, **k: None)
    set_default_sandbox(db, world)
    sandbox_env.mode = "loop"
    response = send(client, world, "do a lot in parallel", selection(world["ai_a"]))
    assert response.status_code == 422 and response.json()["error_code"] == CODE, response.text
    cid = conversations(client, world)[0]
    session_id = conv_row(db, cid).session_id
    state = thread_state(f"thread_{hidden_agent_id(db, world)}_{session_id}")
    # Where the limit cuts the run (3 graph steps per tool-using model call in the Chat's chain: history check,
    # model, tools): right after the MODEL node (an AIMessage with 2 parallel tool calls and no answers: the tool
    # tasks are pending) or right after the TOOLS node (the ToolMessages are the last messages).
    after_model = limit in (5, 8)
    assert state["last"] == ("AIMessage" if after_model else "ToolMessage"), state
    assert state["last_tool_calls"] == (2 if after_model else 0) and state["pending_writes"] == 0, state
    runs_after_failed_turn = sum(1 for _, c in ChatFakeProvider.RUNS if c.startswith("echo"))

    sandbox_env.mode = "strict"
    sandbox_env.report = None
    follow_up = send(client, world, "continue", selection(world["ai_a"]), cid)
    assert follow_up.status_code == 200, follow_up.text
    report = sandbox_env.report
    assert report is not None and report["asked"], "the history handed to the model has no tool calls"
    # (a) every tool call of the history is answered exactly once, a synthetic answer included
    assert report["answered_once"], report
    # (b) no tool ran between the start of the continue turn and its first model call
    assert report["runs_at_model_call"] == runs_after_failed_turn, (report, runs_after_failed_turn)
    assert turn_rows(db, cid) == 1
