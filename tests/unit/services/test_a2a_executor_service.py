import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.a2a_executor_service import (
    A2AExecutionResult,
    A2AExecutorService,
    A2AMemoryContext,
)


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

    async def fake_iterate_remote_events(
        agent_arg,
        message_arg,
        user_context=None,
        attachment_files=None,
        langsmith_config=None,
        memory_context=None,
    ):
        captured["agent"] = agent_arg
        captured["message"] = message_arg
        captured["user_context"] = user_context
        captured["attachment_files"] = attachment_files
        captured["langsmith_config"] = langsmith_config
        captured["memory_context"] = memory_context
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
            attachment_files=[{"filename": "photo.png", "file_path": "conversations/1/photo.png", "type": "image"}],
        )

    assert isinstance(result, A2AExecutionResult)
    assert result.text == "final remote reply"
    assert captured["attachment_files"] == [
        {"filename": "photo.png", "file_path": "conversations/1/photo.png", "type": "image"}
    ]
    assert captured["langsmith_config"] is langsmith_config
    assert len(tracing_context_entries) == 1
    assert tracing_context_entries[0]["project_name"] == "demo-project"
    assert len(trace_entries) == 1
    root_trace = trace_entries[0]
    assert root_trace["name"] == "A2A Agent Invocation: Imported A2A Agent"
    assert root_trace["run_type"] == "chain"
    assert root_trace["inputs"] == {
        "message": "hello world",
        "streaming": False,
        "history_messages": 0,
        "continuation_task_id": None,
    }
    assert root_trace["metadata"]["source_type"] == "a2a"
    assert root_trace["metadata"]["remote_skill_id"] == "skill-1"
    assert root_trace["outputs"] == {
        "response": "final remote reply",
        "response_length": len("final remote reply"),
        "streaming": False,
        "remote_task_id": None,
        "remote_context_id": None,
        "remote_task_state": None,
    }


@pytest.mark.asyncio
async def test_stream_reports_direct_langsmith_trace_for_a2a(monkeypatch):
    service = A2AExecutorService()
    agent = _make_agent()
    trace_entries, tracing_context_entries = _install_fake_langsmith(monkeypatch)
    langsmith_config = {"client": object(), "project_name": "demo-project"}
    emitted_events = []

    async def fake_iterate_remote_events(
        agent_arg,
        message_arg,
        user_context=None,
        attachment_files=None,
        langsmith_config=None,
        memory_context=None,
    ):
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
            attachment_files=[{"filename": "brief.pdf", "file_path": "conversations/1/brief.pdf", "type": "pdf"}],
        ):
            emitted_events.append(event)

    assert emitted_events == [
        {"type": "thinking", "data": {"content": "working", "message": "working"}},
        {"type": "token", "data": {"content": "streamed text"}},
    ]
    assert len(tracing_context_entries) == 1
    assert len(trace_entries) == 1
    root_trace = trace_entries[0]
    assert root_trace["inputs"] == {
        "message": "stream this",
        "streaming": True,
        "history_messages": 0,
        "continuation_task_id": None,
    }
    assert root_trace["outputs"] == {
        "response": "streamed text",
        "response_length": len("streamed text"),
        "streaming": True,
        "emitted_token": True,
    }


def test_build_request_message_includes_binary_file_parts(tmp_path):
    service = A2AExecutorService()
    upload_dir = tmp_path / "conversations" / "12"
    upload_dir.mkdir(parents=True)
    (upload_dir / "diagram.png").write_bytes(b"png-bytes")
    (upload_dir / "brief.pdf").write_bytes(b"%PDF-1.4")

    with patch("utils.config.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}):
        message = service._build_request_message(
            "Please review the attachments",
            attachment_files=[
                {
                    "file_id": "img-1",
                    "filename": "diagram.png",
                    "file_path": "conversations/12/diagram.png",
                    "type": "image",
                },
                {
                    "file_id": "pdf-1",
                    "filename": "brief.pdf",
                    "file_path": "conversations/12/brief.pdf",
                    "type": "pdf",
                    "mime_type": "application/pdf",
                },
            ],
        )

    assert message.role.value == "user"
    assert len(message.parts) == 3
    assert message.parts[0].root.kind == "text"
    assert message.parts[0].root.text == "Please review the attachments"

    image_part = message.parts[1].root
    assert image_part.kind == "file"
    assert image_part.file.name == "diagram.png"
    assert image_part.file.mime_type == "image/png"
    assert image_part.metadata == {"file_id": "img-1", "file_type": "image"}

    pdf_part = message.parts[2].root
    assert pdf_part.kind == "file"
    assert pdf_part.file.name == "brief.pdf"
    assert pdf_part.file.mime_type == "application/pdf"
    assert pdf_part.metadata == {"file_id": "pdf-1", "file_type": "pdf"}


def test_build_request_message_skips_unreadable_attachments(tmp_path):
    service = A2AExecutorService()

    with patch("utils.config.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path)}):
        message = service._build_request_message(
            "Hello",
            attachment_files=[
                {
                    "file_id": "missing-1",
                    "filename": "missing.png",
                    "file_path": "conversations/99/missing.png",
                    "type": "image",
                }
            ],
        )

    assert len(message.parts) == 1
    assert message.parts[0].root.text == "Hello"


def test_build_request_message_reuses_remote_task_ids_when_resumable():
    service = A2AExecutorService()
    memory_context = A2AMemoryContext(
        remote_task_id="task-123",
        remote_context_id="ctx-456",
        remote_task_state="input-required",
    )

    message = service._build_request_message(
        "Here is the requested follow-up",
        memory_context=memory_context,
    )

    assert getattr(message, "task_id", getattr(message, "taskId", None)) == "task-123"
    assert getattr(message, "context_id", getattr(message, "contextId", None)) == "ctx-456"
    assert "Conversation context from previous turns" not in message.parts[0].root.text


def test_build_request_message_does_not_fallback_to_local_history_when_remote_task_is_terminal():
    service = A2AExecutorService()
    memory_context = A2AMemoryContext(
        history=[
            {"role": "user", "content": "We are discussing quarterly forecasts."},
            {"role": "agent", "content": "Understood. I can keep working from that context."},
        ],
        remote_task_id="task-completed",
        remote_context_id="ctx-456",
        remote_task_state="completed",
    )

    message = service._build_request_message(
        "Please continue with the final recommendation",
        memory_context=memory_context,
    )

    text = message.parts[0].root.text
    assert text == "Please continue with the final recommendation"
    assert getattr(message, "referenceTaskIds", None) in (None, [])
