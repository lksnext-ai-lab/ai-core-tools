import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.a2a_executor_service import A2AExecutorService


class _RecordingRun:
    def __init__(self, entry):
        self.entry = entry

    def end(self, outputs=None):
        self.entry["outputs"] = outputs


class _RecordingContextManager:
    def __init__(self, entry, return_run=False):
        self.entry = entry
        self.return_run = return_run

    def __enter__(self):
        return _RecordingRun(self.entry) if self.return_run else None

    def __exit__(self, exc_type, exc, tb):
        return False


def _install_fake_langsmith(monkeypatch):
    trace_entries = []
    tracing_context_entries = []

    fake_langsmith = types.SimpleNamespace()

    def trace(name, run_type="chain", **kwargs):
        entry = {
            "name": name,
            "run_type": run_type,
            **kwargs,
        }
        trace_entries.append(entry)
        return _RecordingContextManager(entry, return_run=True)

    def tracing_context(**kwargs):
        tracing_context_entries.append(kwargs)
        return _RecordingContextManager(kwargs, return_run=False)

    fake_langsmith.trace = trace
    fake_langsmith.tracing_context = tracing_context
    monkeypatch.setitem(sys.modules, "langsmith", fake_langsmith)
    return trace_entries, tracing_context_entries


def _make_agent():
    return SimpleNamespace(
        agent_id=7,
        app_id=42,
        name="Imported A2A Agent",
        a2a_config=SimpleNamespace(
            card_url="https://example.com/.well-known/agent-card.json",
            remote_agent_id="remote-agent-1",
            remote_skill_id="skill-1",
            remote_skill_name="Summarize",
            health_status="healthy",
            sync_status="synced",
        ),
    )


@pytest.mark.asyncio
async def test_execute_reports_direct_langsmith_trace_for_a2a(monkeypatch):
    service = A2AExecutorService()
    agent = _make_agent()
    trace_entries, tracing_context_entries = _install_fake_langsmith(monkeypatch)
    langsmith_config = {"client": object(), "project_name": "demo-project"}
    captured = {}

    async def fake_iterate_remote_events(agent_arg, message_arg, user_context=None, langsmith_config=None):
        captured["agent"] = agent_arg
        captured["message"] = message_arg
        captured["user_context"] = user_context
        captured["langsmith_config"] = langsmith_config
        yield {"type": "token", "data": {"content": "partial"}}
        yield {"type": "final", "data": {"content": "final remote reply"}}

    with (
        patch.object(service, "_get_langsmith_config", return_value=langsmith_config),
        patch.object(service, "_iterate_remote_events", new=fake_iterate_remote_events),
    ):
        result = await service.execute(
            agent,
            "hello world",
            user_context={"app_id": 42, "user_id": 99},
        )

    assert result == "final remote reply"
    assert captured["langsmith_config"] is langsmith_config
    assert len(tracing_context_entries) == 1
    assert tracing_context_entries[0]["project_name"] == "demo-project"
    assert len(trace_entries) == 1
    root_trace = trace_entries[0]
    assert root_trace["name"] == "A2A Agent Invocation: Imported A2A Agent"
    assert root_trace["run_type"] == "chain"
    assert root_trace["inputs"] == {"message": "hello world", "streaming": False}
    assert root_trace["metadata"]["source_type"] == "a2a"
    assert root_trace["metadata"]["remote_skill_id"] == "skill-1"
    assert root_trace["outputs"] == {
        "response": "final remote reply",
        "response_length": len("final remote reply"),
        "streaming": False,
    }


@pytest.mark.asyncio
async def test_stream_reports_direct_langsmith_trace_for_a2a(monkeypatch):
    service = A2AExecutorService()
    agent = _make_agent()
    trace_entries, tracing_context_entries = _install_fake_langsmith(monkeypatch)
    langsmith_config = {"client": object(), "project_name": "demo-project"}
    emitted_events = []

    async def fake_iterate_remote_events(agent_arg, message_arg, user_context=None, langsmith_config=None):
        yield {"type": "thinking", "data": {"content": "working", "message": "working"}}
        yield {"type": "token", "data": {"content": "streamed text"}}
        yield {"type": "final", "data": {"content": "streamed text"}}

    with (
        patch.object(service, "_get_langsmith_config", return_value=langsmith_config),
        patch.object(service, "_iterate_remote_events", new=fake_iterate_remote_events),
    ):
        async for event in service.stream(
            agent,
            "stream this",
            user_context={"app_id": 42, "user_id": 99},
        ):
            emitted_events.append(event)

    assert emitted_events == [
        {"type": "thinking", "data": {"content": "working", "message": "working"}},
        {"type": "token", "data": {"content": "streamed text"}},
    ]
    assert len(tracing_context_entries) == 1
    assert len(trace_entries) == 1
    root_trace = trace_entries[0]
    assert root_trace["inputs"] == {"message": "stream this", "streaming": True}
    assert root_trace["outputs"] == {
        "response": "streamed text",
        "response_length": len("streamed text"),
        "streaming": True,
        "emitted_token": True,
    }
