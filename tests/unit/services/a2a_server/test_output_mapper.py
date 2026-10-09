"""Unit tests for ``services.a2a_server.output_mapper`` (step_015).

Pure-logic module: no DB, no SDK event queue, no SSE text anywhere. The
clock used for coalescing is always injected (a plain float "now"), never
``time.time()``/``time.monotonic()``, so these tests control it exactly.
"""

import ast
import os
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from services.a2a_server.output_mapper import (
    AppendText,
    DefaultFileResolver,
    Fail,
    Final,
    FileResolution,
    FileResolver,
    ResponseArtifactMapper,
    StatusMessage,
    sanitize_error,
)
from tools.streaming_utils import AgentStreamEvent
from utils.security import verify_expiring_signature

OUTPUT_MAPPER_PATH = Path(__file__).resolve().parents[4] / "backend" / "services" / "a2a_server" / "output_mapper.py"


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _StubFileResolver:
    """Returns a pre-baked :class:`FileResolution` for one known file_id."""

    def __init__(self, resolutions: dict):
        self._resolutions = resolutions

    async def resolve(self, file_id: str) -> Optional[FileResolution]:
        return self._resolutions.get(file_id)


def _token(content: str) -> AgentStreamEvent:
    return AgentStreamEvent("token", {"content": content})


def _done(response, *, structured=False, parsed_response=None, files_data=None, conversation_id=1):
    return AgentStreamEvent(
        "done",
        {"response": response, "conversation_id": conversation_id, "files": files_data or []},
        extra={
            "structured": structured,
            "parsed_response": parsed_response,
            "files_data": files_data or [],
            "conversation_id": conversation_id,
        },
    )


def _error(error_kind: str, *, status_code=None, detail=None, error_code="SomeError"):
    extra = {"error_code": error_code, "error_kind": error_kind}
    if status_code is not None:
        extra["status_code"] = status_code
    if detail is not None:
        extra["detail"] = detail
    return AgentStreamEvent("error", {"message": "Agent execution failed"}, extra=extra)


def _final_text(final: Final) -> str:
    """Concatenate every text ``Part`` in a ``Final`` action (should be ≤1)."""
    return "".join(part.text for part in final.parts if part.WhichOneof("content") == "text")


# ---------------------------------------------------------------------------
# Token concatenation / coalescing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_concatenation_equals_final_text():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    now = 1000.0
    sent = []

    for chunk in ("Hello", ", ", "world", "!"):
        action = mapper.handle_token(chunk, now)
        if action is not None:
            sent.append(action.text)
        now += 0.01  # well within the coalescing window after the first flush

    actions = await mapper.apply(_done("Hello, world!"), now)
    drained = [a for a in actions if isinstance(a, AppendText)]
    finals = [a for a in actions if isinstance(a, Final)]
    assert len(finals) == 1

    full_text = "".join(sent) + "".join(a.text for a in drained) + _final_text(finals[0])
    assert full_text == "Hello, world!"


def test_first_token_flushes_immediately():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    action = mapper.handle_token("first", now=100.0)
    assert action == AppendText("first")


def test_coalescing_window_with_injected_clock():
    mapper = ResponseArtifactMapper(coalesce_ms=250)

    first = mapper.handle_token("a", now=0.0)
    assert first == AppendText("a")  # first chunk always flushes

    # Within the window: buffered, not flushed yet.
    assert mapper.handle_token("b", now=0.1) is None
    assert mapper.flush_due(now=0.2) is None

    # Window elapses (>= 250ms since the buffer started holding "b").
    assert mapper.flush_due(now=0.35) is None  # still buffered from handle_token's own check
    late = mapper.handle_token("c", now=0.36)
    assert late == AppendText("bc")


def test_drain_flushes_remaining_buffer_once():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    mapper.handle_token("first", now=0.0)
    mapper.handle_token("second", now=0.01)
    assert mapper.drain() == AppendText("second")
    assert mapper.drain() is None


# ---------------------------------------------------------------------------
# Structured output -> DataPart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structured_response_produces_data_part():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    parsed = {"answer": 42, "tags": ["a", "b"]}
    actions = await mapper.apply(
        _done(parsed, structured=True, parsed_response=parsed), now=0.0
    )
    final = next(a for a in actions if isinstance(a, Final))
    data_parts = [p for p in final.parts if p.WhichOneof("content") == "data"]
    assert len(data_parts) == 1

    from google.protobuf.json_format import MessageToDict

    assert MessageToDict(data_parts[0].data) == {"answer": 42.0, "tags": ["a", "b"]}
    # AC-22: a DataPart's media_type is always application/json.
    assert data_parts[0].media_type == "application/json"


@pytest.mark.asyncio
async def test_non_structured_done_has_no_data_part():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    actions = await mapper.apply(_done("plain text"), now=0.0)
    final = next(a for a in actions if isinstance(a, Final))
    assert not [p for p in final.parts if p.WhichOneof("content") == "data"]


# ---------------------------------------------------------------------------
# Files: inline vs. signed URL (RD-1, AC-23)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_small_file_is_inlined_as_bytes(tmp_path):
    content = b"x" * (1024 * 1024)  # 1 MiB
    file_path = tmp_path / "small.bin"
    file_path.write_bytes(content)

    resolver = _StubFileResolver(
        {
            "file-1": FileResolution(
                abs_path=str(file_path),
                rel_path="conversations/1/small.bin",
                size=len(content),
                media_type="application/octet-stream",
            )
        }
    )
    mapper = ResponseArtifactMapper(
        coalesce_ms=250,
        file_resolver=resolver,
        base_url="https://mattin.example",
        identity="a2a-7",
        inline_file_max_bytes=5 * 1024 * 1024,
    )
    actions = await mapper.apply(
        _done(
            "done",
            files_data=[{"file_id": "file-1", "filename": "small.bin", "file_type": "document"}],
        ),
        now=0.0,
    )
    final = next(a for a in actions if isinstance(a, Final))
    file_parts = [p for p in final.parts if p.WhichOneof("content") == "raw"]
    assert len(file_parts) == 1
    part = file_parts[0]
    assert part.raw == content
    assert part.filename == "small.bin"
    assert part.media_type == "application/octet-stream"
    assert not [p for p in final.parts if p.WhichOneof("content") == "url"]


@pytest.mark.asyncio
async def test_large_file_becomes_a_signed_expiring_url(tmp_path):
    file_path = tmp_path / "large.bin"
    file_path.write_bytes(b"y")  # content irrelevant; size is faked via FileResolution

    resolver = _StubFileResolver(
        {
            "file-2": FileResolution(
                abs_path=str(file_path),
                rel_path="conversations/1/large.bin",
                size=6 * 1024 * 1024,  # 6 MiB, over the 5 MiB cap
                media_type="application/pdf",
            )
        }
    )
    mapper = ResponseArtifactMapper(
        coalesce_ms=250,
        file_resolver=resolver,
        base_url="https://mattin.example",
        identity="a2a-7",
        file_url_ttl_seconds=3600,
        inline_file_max_bytes=5 * 1024 * 1024,
    )
    actions = await mapper.apply(
        _done(
            "done",
            files_data=[{"file_id": "file-2", "filename": "large.pdf", "file_type": "document"}],
        ),
        now=0.0,
    )
    final = next(a for a in actions if isinstance(a, Final))
    url_parts = [p for p in final.parts if p.WhichOneof("content") == "url"]
    assert len(url_parts) == 1
    part = url_parts[0]
    assert part.filename == "large.pdf"
    assert part.media_type == "application/pdf"

    parsed = urlsplit(part.url)
    query = parse_qs(parsed.query)
    assert "exp" in query and "sig" in query
    assert query["user"] == ["a2a-7"]

    rel_path = unquote(parsed.path.split("/static/", 1)[1])
    assert verify_expiring_signature(
        rel_path,
        "a2a-7",
        query["sig"][0],
        int(query["exp"][0]),
        filename="large.pdf",
        now=int(time.time()),
    )


@pytest.mark.asyncio
async def test_missing_file_resolution_is_skipped_not_raised():
    resolver = _StubFileResolver({})
    mapper = ResponseArtifactMapper(
        coalesce_ms=250, file_resolver=resolver, base_url="https://x", identity="a2a-1"
    )
    actions = await mapper.apply(
        _done("done", files_data=[{"file_id": "missing", "filename": "a.bin", "file_type": "document"}]),
        now=0.0,
    )
    final = next(a for a in actions if isinstance(a, Final))
    assert not [p for p in final.parts if p.WhichOneof("content") in ("raw", "url")]


def test_identity_required_when_base_url_is_set():
    with pytest.raises(ValueError):
        ResponseArtifactMapper(coalesce_ms=250, base_url="https://mattin.example", identity="")


def test_no_base_url_is_fine_without_identity():
    # Doesn't raise: without a base_url there is never a signed URL to build.
    ResponseArtifactMapper(coalesce_ms=250, base_url=None, identity="")


@pytest.mark.asyncio
async def test_inline_size_is_rechecked_on_disk_at_read_time(tmp_path):
    """A resolver's reported size can be stale; the real on-disk size always wins."""
    file_path = tmp_path / "grew.bin"
    file_path.write_bytes(b"z" * 1000)  # actually 1000 bytes on disk

    resolver = _StubFileResolver(
        {
            "file-3": FileResolution(
                abs_path=str(file_path),
                rel_path="conversations/1/grew.bin",
                size=10,  # stale/lied-about size, under every cap
                media_type="application/octet-stream",
            )
        }
    )
    mapper = ResponseArtifactMapper(
        coalesce_ms=250,
        file_resolver=resolver,
        base_url="https://mattin.example",
        identity="a2a-7",
        inline_file_max_bytes=500,  # the real 1000-byte file is over this cap
    )
    actions = await mapper.apply(
        _done("done", files_data=[{"file_id": "file-3", "filename": "grew.bin", "file_type": "document"}]),
        now=0.0,
    )
    final = next(a for a in actions if isinstance(a, Final))
    # Never inlined despite the resolver's (stale) size passing the cap.
    assert not [p for p in final.parts if p.WhichOneof("content") == "raw"]
    url_parts = [p for p in final.parts if p.WhichOneof("content") == "url"]
    assert len(url_parts) == 1


@pytest.mark.asyncio
async def test_running_inline_budget_is_shared_across_files_in_one_turn(tmp_path):
    """Two files individually under the per-file cap can still exhaust the turn budget."""
    first_path = tmp_path / "first.bin"
    first_path.write_bytes(b"a" * 60)
    second_path = tmp_path / "second.bin"
    second_path.write_bytes(b"b" * 60)

    resolver = _StubFileResolver(
        {
            "first": FileResolution(
                abs_path=str(first_path), rel_path="first.bin", size=60, media_type="application/octet-stream"
            ),
            "second": FileResolution(
                abs_path=str(second_path), rel_path="second.bin", size=60, media_type="application/octet-stream"
            ),
        }
    )
    mapper = ResponseArtifactMapper(
        coalesce_ms=250,
        file_resolver=resolver,
        base_url="https://mattin.example",
        identity="a2a-7",
        inline_file_max_bytes=100,  # each file (60B) fits alone, but not both (120B > 100B)
    )
    actions = await mapper.apply(
        _done(
            "done",
            files_data=[
                {"file_id": "first", "filename": "first.bin", "file_type": "document"},
                {"file_id": "second", "filename": "second.bin", "file_type": "document"},
            ],
        ),
        now=0.0,
    )
    final = next(a for a in actions if isinstance(a, Final))
    raw_parts = [p for p in final.parts if p.WhichOneof("content") == "raw"]
    url_parts = [p for p in final.parts if p.WhichOneof("content") == "url"]
    # The first file fits the fresh budget and is inlined...
    assert len(raw_parts) == 1
    assert raw_parts[0].raw == b"a" * 60
    # ...which exhausts the turn's inline budget, so the second falls back to a URL
    # even though it is, by itself, under the per-file cap.
    assert len(url_parts) == 1
    assert "second.bin" in url_parts[0].url


# ---------------------------------------------------------------------------
# Error sanitization (RB-7: on error_kind, never error_code)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_error_is_sanitized():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    actions = await mapper.apply(_error("connection", error_code="OperationalError"), now=0.0)
    assert actions == [Fail("Temporary connection error, please retry.")]


@pytest.mark.asyncio
async def test_agent_failure_error_is_sanitized_generic():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    actions = await mapper.apply(_error("agent_failure", error_code="ValueError"), now=0.0)
    assert actions == [Fail("Agent execution failed.")]


@pytest.mark.asyncio
async def test_serialization_and_incomplete_turn_errors_are_generic():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    for kind in ("serialization", "incomplete_turn"):
        actions = await mapper.apply(_error(kind), now=0.0)
        assert actions == [Fail("Agent execution failed.")]


@pytest.mark.asyncio
async def test_http_4xx_error_surfaces_detail():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    actions = await mapper.apply(
        _error("http", status_code=403, detail="Conversation does not belong to this caller."),
        now=0.0,
    )
    assert actions == [Fail("Conversation does not belong to this caller.")]


@pytest.mark.asyncio
async def test_http_5xx_error_never_surfaces_detail():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    actions = await mapper.apply(_error("http", status_code=500, detail=None), now=0.0)
    assert actions == [Fail("Agent execution failed.")]


def test_sanitize_error_unknown_kind_is_generic():
    assert sanitize_error({"error_kind": "something_new"}) == "Agent execution failed."
    assert sanitize_error(None) == "Agent execution failed."
    assert sanitize_error({}) == "Agent execution failed."


def test_sanitize_error_never_keyed_on_error_code():
    # Same unrecognized error_kind, wildly different error_code: identical message.
    a = sanitize_error({"error_kind": "agent_failure", "error_code": "ValueError"})
    b = sanitize_error({"error_kind": "agent_failure", "error_code": "KeyError"})
    assert a == b == "Agent execution failed."


# ---------------------------------------------------------------------------
# done.data["response"] authoritative over token concatenation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authoritative_response_appends_only_the_remainder():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    mapper.handle_token("Hello", now=0.0)  # flushes immediately -> sent_text == "Hello"

    # _finalize_turn appended a file marker after the last streamed token.
    actions = await mapper.apply(_done("Hello [file:report.pdf]"), now=1.0)
    final = next(a for a in actions if isinstance(a, Final))
    assert _final_text(final) == " [file:report.pdf]"


@pytest.mark.asyncio
async def test_authoritative_response_wins_outright_on_divergence():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    mapper.handle_token("partial attempt", now=0.0)

    # The retry path replaced the turn's answer outright, with no shared prefix.
    actions = await mapper.apply(_done("Completely different final answer."), now=1.0)
    final = next(a for a in actions if isinstance(a, Final))
    assert _final_text(final) == "Completely different final answer."


@pytest.mark.asyncio
async def test_structured_only_turn_with_no_tokens_renders_json_text():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    parsed = {"a": 1}
    actions = await mapper.apply(_done(parsed, structured=True, parsed_response=parsed), now=0.0)
    final = next(a for a in actions if isinstance(a, Final))
    assert _final_text(final) == '{"a": 1}'


# ---------------------------------------------------------------------------
# Status updates (off by default; generic text only when enabled)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_and_thinking_events_produce_nothing_by_default():
    mapper = ResponseArtifactMapper(coalesce_ms=250, status_updates=False)
    for event in (
        AgentStreamEvent("thinking", {"message": "Searching the web..."}),
        AgentStreamEvent("tool_start", {"tool_name": "web_search", "args": {"q": "secret"}}),
        AgentStreamEvent("tool_end", {"tool_name": "web_search", "tool_output": "secret result"}),
        AgentStreamEvent("code_output", {"line": "print(1)"}),
    ):
        assert await mapper.apply(event, now=0.0) == []


@pytest.mark.asyncio
async def test_status_updates_enabled_emits_generic_text_never_tool_args():
    mapper = ResponseArtifactMapper(coalesce_ms=250, status_updates=True)
    actions = await mapper.apply(
        AgentStreamEvent("tool_start", {"tool_name": "web_search", "args": {"q": "secret-query"}}),
        now=0.0,
    )
    assert len(actions) == 1
    assert isinstance(actions[0], StatusMessage)
    assert "secret-query" not in actions[0].text

    actions = await mapper.apply(
        AgentStreamEvent("tool_end", {"tool_name": "web_search", "tool_output": "secret-output"}),
        now=0.0,
    )
    assert len(actions) == 1
    assert isinstance(actions[0], StatusMessage)
    assert "secret-output" not in actions[0].text


@pytest.mark.asyncio
async def test_status_updates_are_fixed_strings_only():
    """Status text is one of exactly two fixed strings -- never the event's own text."""
    mapper = ResponseArtifactMapper(coalesce_ms=250, status_updates=True)

    actions = await mapper.apply(
        AgentStreamEvent("thinking", {"message": "secret"}), now=0.0
    )
    assert actions == [StatusMessage("Working...")]

    actions = await mapper.apply(
        AgentStreamEvent("tool_start", {"tool_name": "internal_secret_tool"}), now=0.0
    )
    assert actions == [StatusMessage("Using a tool...")]
    assert "internal_secret_tool" not in actions[0].text

    actions = await mapper.apply(
        AgentStreamEvent("tool_end", {"tool_name": "internal_secret_tool", "tool_output": "secret"}),
        now=0.0,
    )
    assert actions == [StatusMessage("Working...")]

    actions = await mapper.apply(
        AgentStreamEvent("code_output", {"line": "print('secret')"}), now=0.0
    )
    assert actions == [StatusMessage("Working...")]


@pytest.mark.asyncio
async def test_metadata_event_is_captured_but_produces_no_action():
    mapper = ResponseArtifactMapper(coalesce_ms=250)
    actions = await mapper.apply(
        AgentStreamEvent("metadata", {"conversation_id": 42, "agent_id": 1}), now=0.0
    )
    assert actions == []
    assert mapper.conversation_id == 42


@pytest.mark.asyncio
async def test_never_produces_input_required():
    mapper = ResponseArtifactMapper(coalesce_ms=250, status_updates=True)
    events = [
        AgentStreamEvent("metadata", {"conversation_id": 1}),
        _token("hi"),
        AgentStreamEvent("tool_start", {"tool_name": "x"}),
        AgentStreamEvent("tool_end", {"tool_name": "x"}),
        _error("agent_failure"),
        _done("hi"),
    ]
    for event in events:
        for action in await mapper.apply(event, now=0.0):
            assert not isinstance(action, str) or action != "input_required"
    # No action type even remotely named input_required exists in the module.
    import services.a2a_server.output_mapper as output_mapper

    assert not hasattr(output_mapper, "InputRequired")


# ---------------------------------------------------------------------------
# DefaultFileResolver, against the real FileManagementService session layout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_file_resolver_finds_a_registered_output_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TMP_BASE_FOLDER", str(tmp_path))
    import utils.config as config_module

    config_module.get_app_config.cache_clear() if hasattr(config_module.get_app_config, "cache_clear") else None

    from services.file_management_service import FileManagementService

    fms = FileManagementService()
    out_dir = tmp_path / "outputs"
    out_dir.mkdir()
    produced = out_dir / "report.csv"
    produced.write_bytes(b"a,b\n1,2\n")

    user_context = {"user_id": "u1", "app_id": "app1"}
    new_files = await fms.sync_output_files(
        working_dir=str(out_dir),
        agent_id=99,
        user_context=user_context,
        conversation_id="7",
    )
    assert new_files, "sync_output_files should have registered report.csv"
    file_id = new_files[0].file_id

    resolver = DefaultFileResolver(agent_id=99, user_context=user_context, conversation_id="7")
    resolution = await resolver.resolve(file_id)
    assert resolution is not None
    assert os.path.isfile(resolution.abs_path)
    assert resolution.size == len(b"a,b\n1,2\n")


@pytest.mark.asyncio
async def test_default_file_resolver_returns_none_for_unknown_file_id(tmp_path, monkeypatch):
    monkeypatch.setenv("TMP_BASE_FOLDER", str(tmp_path))
    resolver = DefaultFileResolver(agent_id=1, user_context=None, conversation_id=None)
    assert await resolver.resolve("does-not-exist") is None


# ---------------------------------------------------------------------------
# DefaultFileResolver: session isolation and path containment
# ---------------------------------------------------------------------------


async def _register_report(tmp_path, *, agent_id, user_context, conversation_id):
    from services.file_management_service import FileManagementService

    fms = FileManagementService()
    out_dir = tmp_path / f"outputs-{agent_id}-{conversation_id}"
    out_dir.mkdir()
    (out_dir / "report.csv").write_bytes(b"a,b\n1,2\n")

    new_files = await fms.sync_output_files(
        working_dir=str(out_dir),
        agent_id=agent_id,
        user_context=user_context,
        conversation_id=conversation_id,
    )
    assert new_files, "sync_output_files should have registered report.csv"
    return new_files[0].file_id


@pytest.mark.asyncio
async def test_default_file_resolver_is_isolated_by_conversation(tmp_path, monkeypatch):
    monkeypatch.setenv("TMP_BASE_FOLDER", str(tmp_path))
    user_context = {"user_id": "u1", "app_id": "app1"}
    file_id = await _register_report(tmp_path, agent_id=99, user_context=user_context, conversation_id="7")

    same = DefaultFileResolver(agent_id=99, user_context=user_context, conversation_id="7")
    assert await same.resolve(file_id) is not None

    other_conversation = DefaultFileResolver(agent_id=99, user_context=user_context, conversation_id="8")
    assert await other_conversation.resolve(file_id) is None


@pytest.mark.asyncio
async def test_default_file_resolver_is_isolated_by_app(tmp_path, monkeypatch):
    monkeypatch.setenv("TMP_BASE_FOLDER", str(tmp_path))
    file_id = await _register_report(
        tmp_path, agent_id=99, user_context={"user_id": "u1", "app_id": "app1"}, conversation_id="7"
    )

    other_app = DefaultFileResolver(
        agent_id=99, user_context={"user_id": "u1", "app_id": "app2"}, conversation_id="7"
    )
    assert await other_app.resolve(file_id) is None


@pytest.mark.asyncio
async def test_default_file_resolver_is_isolated_by_user(tmp_path, monkeypatch):
    monkeypatch.setenv("TMP_BASE_FOLDER", str(tmp_path))
    file_id = await _register_report(
        tmp_path, agent_id=99, user_context={"user_id": "u1", "app_id": "app1"}, conversation_id="7"
    )

    other_user = DefaultFileResolver(
        agent_id=99, user_context={"user_id": "u2", "app_id": "app1"}, conversation_id="7"
    )
    assert await other_user.resolve(file_id) is None


@pytest.mark.asyncio
async def test_default_file_resolver_rejects_a_traversal_path_in_the_sidecar(tmp_path, monkeypatch):
    """A tampered/crafted sidecar's file_path must never resolve outside TMP_BASE_FOLDER."""
    import json as json_module

    from services.file_management_service import FileManagementService

    monkeypatch.setenv("TMP_BASE_FOLDER", str(tmp_path))
    fms = FileManagementService()
    user_context = {"user_id": "u1", "app_id": "app1"}
    session_key = fms._get_session_key(99, user_context, "7")
    session_dir = tmp_path / "persistent" / session_key
    session_dir.mkdir(parents=True)
    (session_dir / "evil.json").write_text(
        json_module.dumps(
            {
                "file_id": "evil",
                "filename": "passwd",
                "file_type": "text",
                "file_path": "../../etc/passwd",
            }
        )
    )
    (session_dir / "evil.content").write_text("ignored")

    resolver = DefaultFileResolver(agent_id=99, user_context=user_context, conversation_id="7")
    assert await resolver.resolve("evil") is None


@pytest.mark.asyncio
async def test_default_file_resolver_rejects_a_symlink_escaping_tmp_base(tmp_path, monkeypatch):
    """A registered output file that is a symlink pointing outside TMP_BASE_FOLDER is refused."""
    monkeypatch.setenv("TMP_BASE_FOLDER", str(tmp_path))

    outside_target = tmp_path.parent / "output-mapper-outside-secret.txt"
    outside_target.write_text("top secret")
    try:
        file_id = None
        from services.file_management_service import FileManagementService

        fms = FileManagementService()
        out_dir = tmp_path / "outputs-symlink"
        out_dir.mkdir()
        link_path = out_dir / "escape_link"
        link_path.symlink_to(outside_target)

        user_context = {"user_id": "u1", "app_id": "app1"}
        new_files = await fms.sync_output_files(
            working_dir=str(out_dir),
            agent_id=101,
            user_context=user_context,
            conversation_id="7",
        )
        assert new_files, "sync_output_files should have registered the symlink"
        file_id = new_files[0].file_id

        resolver = DefaultFileResolver(agent_id=101, user_context=user_context, conversation_id="7")
        assert await resolver.resolve(file_id) is None
    finally:
        outside_target.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# AC-15: no SSE parsing/rendering anywhere in this module
# ---------------------------------------------------------------------------


def test_module_never_builds_or_parses_sse_text():
    source = OUTPUT_MAPPER_PATH.read_text()

    tree = ast.parse(source)
    imported_names = set()
    string_literals = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            string_literals.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    string_literals.append(value.value)

    # Only string *literals* (code, not prose comments/docstrings) matter
    # here -- the raw SSE wire-format prefix `format_sse_event` emits.
    assert not any(literal.startswith("data: ") for literal in string_literals)
    assert "format_sse_event" not in imported_names
