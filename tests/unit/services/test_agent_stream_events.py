"""Unit tests for ``AgentStreamingService.stream_agent_events`` — the typed
streaming seam (AD-5, plan step_008).

These mirror the golden SSE scenarios in
``tests/unit/services/test_agent_streaming_golden.py`` but assert the typed
``AgentStreamEvent`` sequence (type/data/extra) directly, instead of the
rendered SSE strings, plus the cancellation-propagation contract that lets a
non-SSE consumer (e.g. the A2A execution bridge) stop the underlying
``astream`` loop by closing the generator.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import psycopg.errors
import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from tools.streaming_utils import AgentStreamEvent


# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_agent_streaming_golden.py)
# ---------------------------------------------------------------------------


def _make_ctx(
    *,
    has_memory: bool = False,
    conversation=None,
    session_id_for_cache=None,
):
    fresh_agent = SimpleNamespace(agent_id=1, has_memory=has_memory, app=None)
    agent = SimpleNamespace(name="TestAgent", has_memory=has_memory)
    return SimpleNamespace(
        agent_id=1,
        agent=agent,
        fresh_agent=fresh_agent,
        effective_conv_id=297,
        conversation=conversation,
        session_id_for_cache=session_id_for_cache,
        user_context={"user_id": "u1"},
        image_files=[],
        processed_files=[],
        enhanced_message="hello",
        search_params={},
        working_dir="/tmp/work",
        sandbox_handle=None,
        sandbox_provider=None,
        sandbox_session_key=None,
    )


def _make_chain(chunks):
    async def _gen():
        for item in chunks:
            yield item

    chain = MagicMock()
    chain.astream.return_value = _gen()
    return chain


class _StreamHarness:
    def __init__(self):
        self.recorded_kwargs: dict = {}

    def recorder(self, **kwargs):
        self.recorded_kwargs.update(kwargs)


def _build_service(ctx, finalize_return=None):
    from services.agent_streaming_service import AgentStreamingService

    execution_service = MagicMock()
    execution_service._prepare_turn = AsyncMock(return_value=ctx)
    execution_service._finalize_turn = AsyncMock(
        return_value=finalize_return
        or {
            "parsed_response": "hello world",
            "effective_conv_id": 297,
            "files_data": [],
        }
    )
    execution_service._begin_sandbox_turn = MagicMock(return_value=False)
    execution_service._end_sandbox_turn = MagicMock()

    service = AgentStreamingService()
    service.execution_service = execution_service
    return service


def _patches(create_agent_mock, harness, extra_patches=None):
    patches = [
        patch("services.agent_streaming_service.create_agent", create_agent_mock),
        patch(
            "services.agent_streaming_service.prepare_agent_config",
            return_value={"configurable": {}},
        ),
        patch(
            "services.agent_streaming_service.build_human_message",
            return_value=SimpleNamespace(content="hello"),
        ),
        patch(
            "services.agent_streaming_service.resolve_langsmith_settings",
            return_value=None,
        ),
        patch(
            "services.agent_streaming_service.record_agent_execution",
            side_effect=harness.recorder,
        ),
    ]
    if extra_patches:
        patches.extend(extra_patches)
    return patches


async def _run_events(
    *,
    ctx,
    create_agent_mock,
    finalize_return=None,
    extra_patches=None,
):
    """Drive ``stream_agent_events`` to completion and return
    (list_of_AgentStreamEvent, harness)."""
    harness = _StreamHarness()
    service = _build_service(ctx, finalize_return=finalize_return)
    db = MagicMock()

    from contextlib import ExitStack

    with ExitStack() as stack:
        for p in _patches(create_agent_mock, harness, extra_patches):
            stack.enter_context(p)

        events = [
            ev
            async for ev in service.stream_agent_events(
                agent_id=1,
                message="hello",
                file_references=[],
                user_context={"user_id": "u1"},
                conversation_id=297,
                db=db,
            )
        ]

    return events, harness


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


class TestAgentStreamEventsTyped:
    """Typed mirror of the golden SSE scenarios — asserts AgentStreamEvent
    objects (type/data/extra), not rendered SSE strings."""

    @pytest.mark.asyncio
    async def test_plain_tokens(self):
        chain = _make_chain(
            [
                ("messages", (AIMessageChunk(content="Hello"), {})),
                ("messages", (AIMessageChunk(content=" world"), {})),
            ]
        )
        create_agent = AsyncMock(return_value=(chain, None))

        events, harness = await _run_events(ctx=_make_ctx(), create_agent_mock=create_agent)

        assert events == [
            AgentStreamEvent(
                "metadata",
                {
                    "conversation_id": 297,
                    "session_id": None,
                    "agent_id": 1,
                    "agent_name": "TestAgent",
                    "has_memory": False,
                },
            ),
            AgentStreamEvent("token", {"content": "Hello"}),
            AgentStreamEvent("token", {"content": " world"}),
            AgentStreamEvent(
                "done",
                {"response": "hello world", "conversation_id": 297, "files": [], "status": "completed"},
                extra={
                    "structured": False,
                    "parsed_response": "hello world",
                    "files_data": [],
                    "conversation_id": 297,
                },
            ),
        ]
        assert harness.recorded_kwargs["status"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_tool_start_and_tool_end(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "web_search", "id": "call_1", "args": {"q": "x"}}],
        )
        tool_msg = ToolMessage(
            content="result-content", tool_call_id="call_1", name="web_search"
        )
        chain = _make_chain(
            [
                ("updates", {"agent": {"messages": [ai_msg]}}),
                ("updates", {"tools": {"messages": [tool_msg]}}),
            ]
        )
        create_agent = AsyncMock(return_value=(chain, None))

        events, harness = await _run_events(ctx=_make_ctx(), create_agent_mock=create_agent)

        assert events[0].type == "metadata"
        assert events[1] == AgentStreamEvent(
            "tool_start",
            {
                "tool_name": "web_search",
                "tool_call_id": "call_1",
                "args": {"q": "x"},
                "tool_input": '{"q": "x"}',
            },
        )
        assert events[2] == AgentStreamEvent(
            "thinking", {"message": "Searching the web...", "tool_name": "web_search"}
        )
        assert events[3] == AgentStreamEvent(
            "tool_end",
            {
                "tool_name": "web_search",
                "tool_call_id": "call_1",
                "tool_output": "result-content",
            },
        )
        assert events[-1].type == "done"
        assert harness.recorded_kwargs["status"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_structured_response_extra_flag_true(self):
        chain = _make_chain(
            [
                ("messages", (AIMessageChunk(content="partial"), {})),
                ("updates", {"model": {"structured_response": {"answer": 42}}}),
            ]
        )
        create_agent = AsyncMock(return_value=(chain, None))

        events, harness = await _run_events(
            ctx=_make_ctx(),
            create_agent_mock=create_agent,
            finalize_return={
                "parsed_response": {"answer": 42},
                "effective_conv_id": 297,
                "files_data": [],
            },
        )

        done = events[-1]
        assert done.type == "done"
        assert done.extra == {
            "structured": True,
            "parsed_response": {"answer": 42},
            "files_data": [],
            "conversation_id": 297,
        }

    @pytest.mark.asyncio
    async def test_finalize_turn_files_data_passthrough(self):
        chain = _make_chain([("messages", (AIMessageChunk(content="hi"), {}))])
        create_agent = AsyncMock(return_value=(chain, None))

        files_data = [{"filename": "out.txt", "file_id": 5}]
        events, _ = await _run_events(
            ctx=_make_ctx(),
            create_agent_mock=create_agent,
            finalize_return={
                "parsed_response": "hi",
                "effective_conv_id": 297,
                "files_data": files_data,
            },
        )

        done = events[-1]
        assert done.data["files"] == files_data
        assert done.extra["files_data"] == files_data
        assert done.extra["structured"] is False

    @pytest.mark.asyncio
    async def test_exception_mid_stream_error_extra_code(self):
        async def _gen():
            yield ("messages", (AIMessageChunk(content="partial"), {}))
            raise RuntimeError("boom")

        chain = MagicMock()
        chain.astream.return_value = _gen()
        create_agent = AsyncMock(return_value=(chain, None))

        events, harness = await _run_events(ctx=_make_ctx(), create_agent_mock=create_agent)

        error_ev = events[-1]
        assert error_ev == AgentStreamEvent(
            "error",
            {"message": "Agent execution failed"},
            extra={"error_code": "RuntimeError", "error_kind": "agent_failure"},
        )
        assert harness.recorded_kwargs["status"] == "ERROR"
        assert harness.recorded_kwargs["error_code"] == "RuntimeError"

    @pytest.mark.asyncio
    async def test_psycopg_operational_error_extra_code(self):
        async def _gen():
            yield ("messages", (AIMessageChunk(content="partial"), {}))
            raise psycopg.OperationalError("conn lost")

        chain = MagicMock()
        chain.astream.return_value = _gen()
        create_agent = AsyncMock(return_value=(chain, None))

        events, _ = await _run_events(ctx=_make_ctx(), create_agent_mock=create_agent)

        error_ev = events[-1]
        assert error_ev == AgentStreamEvent(
            "error",
            {"message": "Connection error, please retry."},
            extra={"error_code": "OperationalError", "error_kind": "connection"},
        )

    @pytest.mark.asyncio
    async def test_missing_tool_output_retry_error_extra_code(self):
        def _make_raising_chain(exc):
            async def _gen():
                raise exc
                yield None  # pragma: no cover

            chain = MagicMock()
            chain.astream.return_value = _gen()
            return chain

        ctx = _make_ctx(
            has_memory=True,
            conversation=SimpleNamespace(session_id="conv_1_297"),
            session_id_for_cache="297",
        )
        first_chain = _make_raising_chain(
            RuntimeError(
                "Error code: 400 - No tool output found for function call call_stale"
            )
        )
        create_agent = AsyncMock(return_value=(first_chain, None))

        extra_patches = [
            patch(
                "services.agent_streaming_service.is_missing_tool_output_error",
                side_effect=lambda exc: "No tool output found" in str(exc),
            ),
            patch(
                "services.agent_streaming_service.CheckpointerCacheService"
                ".get_rollback_checkpoint_id",
                new=AsyncMock(return_value=None),
            ),
        ]

        events, harness = await _run_events(
            ctx=ctx, create_agent_mock=create_agent, extra_patches=extra_patches
        )

        error_ev = events[-1]
        assert error_ev.type == "error"
        assert error_ev.data == {
            "message": "Your last message could not be completed. Please resend it."
        }
        assert error_ev.extra == {
            "error_code": "RuntimeError",
            "error_kind": "incomplete_turn",
        }
        assert harness.recorded_kwargs["status"] == "ERROR"

    @pytest.mark.asyncio
    async def test_http_exception_mid_stream_reports_structured_extra(self):
        """An ``HTTPException`` raised mid-turn (e.g. a downstream check
        rejecting a frozen agent or a quota) must not collapse into the
        generic 'agent_failure' error — the SSE bytes stay identical to the
        generic-exception golden (AC-43/NFR-9), but a non-SSE consumer gets
        the status code and detail in ``extra``. Raised from ``create_agent``
        (after ``_prepare_turn`` has already produced ``ctx``) so metrics are
        still recorded, matching the existing "only record if ctx exists"
        contract."""
        create_agent = AsyncMock(
            side_effect=HTTPException(status_code=403, detail="Agent is frozen")
        )

        harness = _StreamHarness()
        service = _build_service(_make_ctx())
        db = MagicMock()

        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in _patches(create_agent, harness):
                stack.enter_context(p)

            events = [
                ev
                async for ev in service.stream_agent_events(
                    agent_id=1,
                    message="hello",
                    file_references=[],
                    user_context={"user_id": "u1"},
                    conversation_id=297,
                    db=db,
                )
            ]

        assert events[0].type == "metadata"
        assert events[-1] == AgentStreamEvent(
            "error",
            {"message": "Agent execution failed"},
            extra={
                "error_code": "HTTPException",
                "error_kind": "http",
                "status_code": 403,
                "detail": "Agent is frozen",
            },
        )
        assert harness.recorded_kwargs["status"] == "ERROR"
        assert harness.recorded_kwargs["error_code"] == "HTTPException"

    @pytest.mark.asyncio
    async def test_http_exception_5xx_redacts_detail(self):
        create_agent = AsyncMock(
            side_effect=HTTPException(status_code=503, detail="db unreachable: secret-dsn")
        )

        harness = _StreamHarness()
        service = _build_service(_make_ctx())
        db = MagicMock()

        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in _patches(create_agent, harness):
                stack.enter_context(p)

            events = [
                ev
                async for ev in service.stream_agent_events(
                    agent_id=1,
                    message="hello",
                    file_references=[],
                    user_context={"user_id": "u1"},
                    conversation_id=297,
                    db=db,
                )
            ]

        error_ev = events[-1]
        assert error_ev.data == {"message": "Agent execution failed"}
        assert error_ev.extra == {
            "error_code": "HTTPException",
            "error_kind": "http",
            "status_code": 503,
            "detail": None,
        }
        assert harness.recorded_kwargs["error_message"] == "Internal error"

    @pytest.mark.asyncio
    async def test_non_serializable_done_payload_reports_serialization_error(self):
        """``_finalize_turn`` returning a non-JSON-serializable
        ``parsed_response`` must not let ``format_sse_event``'s json.dumps
        raise inside the SSE bridge (where it would be misreported as a
        cancellation) — the seam validates the ``done`` payload itself and
        turns it into one terminal ``error`` event with
        ``error_kind="serialization"``."""
        chain = _make_chain([("messages", (AIMessageChunk(content="hi"), {}))])
        create_agent = AsyncMock(return_value=(chain, None))

        events, harness = await _run_events(
            ctx=_make_ctx(),
            create_agent_mock=create_agent,
            finalize_return={
                "parsed_response": {"x": object()},
                "effective_conv_id": 297,
                "files_data": [],
            },
        )

        assert events[-1].type == "error"
        assert events[-1].data == {"message": "Agent execution failed"}
        assert events[-1].extra["error_kind"] == "serialization"
        assert events[-1].extra["error_code"] == "SerializationError"
        assert harness.recorded_kwargs["status"] == "ERROR"
        assert harness.recorded_kwargs["error_code"] == "SerializationError"

        # The wrapper (stream_agent_chat) must also end cleanly with a real
        # SSE error line — not raise out of format_sse_event's json.dumps —
        # and must not misreport the turn as cancelled.
        from services.agent_streaming_service import AgentStreamingService

        sse_harness = _StreamHarness()
        sse_service = _build_service(
            _make_ctx(),
            finalize_return={
                "parsed_response": {"x": object()},
                "effective_conv_id": 297,
                "files_data": [],
            },
        )
        chain2 = _make_chain([("messages", (AIMessageChunk(content="hi"), {}))])
        create_agent2 = AsyncMock(return_value=(chain2, None))
        db = MagicMock()

        from contextlib import ExitStack

        sse_events = []
        with ExitStack() as stack:
            for p in _patches(create_agent2, sse_harness):
                stack.enter_context(p)

            sse_events = [
                ev
                async for ev in sse_service.stream_agent_chat(
                    agent_id=1,
                    message="hello",
                    file_references=[],
                    user_context={"user_id": "u1"},
                    conversation_id=297,
                    db=db,
                )
            ]

        assert sse_events[-1] == (
            'data: {"type": "error", "data": {"message": "Agent execution failed"}}\n\n'
        )
        assert sse_harness.recorded_kwargs["status"] == "ERROR"
        assert sse_harness.recorded_kwargs["error_code"] == "SerializationError"

    @pytest.mark.asyncio
    async def test_closing_consumer_before_resuming_inner_astream_closes_it_immediately(self):
        """Closing ``stream_agent_events`` before it ever asks the fake
        astream for a second chunk must still close that inner generator
        immediately (``contextlib.aclosing`` around ``agent_chain.astream``),
        proven by a ``finally``-block sentinel rather than a counter that
        could pass vacuously. ``sentinel["resumed"]`` staying ``False`` shows
        the inner generator was torn down at its suspension point and never
        driven forward into its (10s) sleep."""
        sentinel = {"resumed": False, "closed": False}

        async def _gen():
            try:
                yield ("messages", (AIMessageChunk(content="partial"), {}))
                sentinel["resumed"] = True
                await asyncio.sleep(10)
                yield ("messages", (AIMessageChunk(content="more"), {}))  # pragma: no cover
            finally:
                sentinel["closed"] = True

        chain = MagicMock()
        chain.astream.return_value = _gen()
        create_agent = AsyncMock(return_value=(chain, None))

        ctx = _make_ctx()
        harness = _StreamHarness()
        service = _build_service(ctx)
        db = MagicMock()

        from contextlib import ExitStack

        events = []
        with ExitStack() as stack:
            for p in _patches(create_agent, harness):
                stack.enter_context(p)

            gen = service.stream_agent_events(
                agent_id=1,
                message="hello",
                file_references=[],
                user_context={"user_id": "u1"},
                conversation_id=297,
                db=db,
            )
            events.append(await gen.__anext__())  # metadata
            events.append(await gen.__anext__())  # token "partial"
            await asyncio.wait_for(gen.aclose(), timeout=1)

        assert [ev.type for ev in events] == ["metadata", "token"]
        assert sentinel["closed"] is True
        assert sentinel["resumed"] is False
        assert harness.recorded_kwargs["status"] == "ERROR"
        assert harness.recorded_kwargs["error_code"] == "Cancelled"
        assert harness.recorded_kwargs["error_message"] == "Stream cancelled"
        service.execution_service._finalize_turn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_consumer_aclose_right_after_done_records_success_not_cancelled(self):
        """A completed turn's own consumer stopping iteration right after
        ``done`` (exactly what ``contextlib.aclosing.__aexit__`` -> ``aclose()``
        does once it has read the terminal event — the pattern every
        documented consumer uses, including ``stream_agent_chat`` and the A2A
        execution bridge's ``_drain``) must still record ``SUCCESS``.

        Before this fix, ``aclose()`` throws ``GeneratorExit`` back into this
        generator at the still-suspended ``yield`` of ``done`` -- indistinguishable,
        to a bare ``except (CancelledError, GeneratorExit)``, from a real
        mid-turn cancellation -- so every successful A2A turn (and every
        successful SSE turn whose consumer closes promptly) was being
        mis-recorded as ``"Cancelled"``.
        """
        chain = _make_chain([("messages", (AIMessageChunk(content="hi"), {}))])
        create_agent = AsyncMock(return_value=(chain, None))

        ctx = _make_ctx()
        harness = _StreamHarness()
        service = _build_service(ctx)
        db = MagicMock()

        from contextlib import ExitStack

        events = []
        with ExitStack() as stack:
            for p in _patches(create_agent, harness):
                stack.enter_context(p)

            gen = service.stream_agent_events(
                agent_id=1,
                message="hello",
                file_references=[],
                user_context={"user_id": "u1"},
                conversation_id=297,
                db=db,
            )
            try:
                while True:
                    event = await gen.__anext__()
                    events.append(event)
                    if event.type == "done":
                        break
            finally:
                # Exactly what `contextlib.aclosing`'s `__aexit__` does once a
                # consumer has what it needs -- the reproduction for the bug
                # this test guards against.
                await asyncio.wait_for(gen.aclose(), timeout=1)

        assert [ev.type for ev in events] == ["metadata", "token", "done"]
        assert harness.recorded_kwargs["status"] == "SUCCESS"
        assert harness.recorded_kwargs.get("error_code") is None
        assert harness.recorded_kwargs.get("error_message") is None

    @pytest.mark.asyncio
    async def test_cancelling_consumer_task_blocked_in_anext_stops_inner_sleep(self):
        """Cancelling the *task* that is awaiting ``gen.__anext__()`` while
        the inner fake astream is suspended inside an ``asyncio.sleep`` must
        stop that sleep immediately — the contract AD-6/AD-8 (the A2A
        execution bridge's remote-cancel path) depends on: the LLM/tool call
        the inner generator represents must actually be torn down, not left
        running after the turn is recorded ``"Cancelled"``."""
        sentinel = {"resumed": False, "closed": False}
        entered_sleep = asyncio.Event()

        async def _gen():
            try:
                yield ("messages", (AIMessageChunk(content="partial"), {}))
                sentinel["resumed"] = True
                entered_sleep.set()
                await asyncio.sleep(10)
                sentinel["resumed_past_sleep"] = True  # pragma: no cover
                yield ("messages", (AIMessageChunk(content="more"), {}))  # pragma: no cover
            finally:
                sentinel["closed"] = True

        chain = MagicMock()
        chain.astream.return_value = _gen()
        create_agent = AsyncMock(return_value=(chain, None))

        ctx = _make_ctx()
        harness = _StreamHarness()
        service = _build_service(ctx)
        db = MagicMock()

        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in _patches(create_agent, harness):
                stack.enter_context(p)

            gen = service.stream_agent_events(
                agent_id=1,
                message="hello",
                file_references=[],
                user_context={"user_id": "u1"},
                conversation_id=297,
                db=db,
            )
            meta = await gen.__anext__()
            token1 = await gen.__anext__()
            assert meta.type == "metadata"
            assert token1.type == "token"

            # Drive the outer generator past its token yield so it asks the
            # inner fake astream for a second chunk — that resumes the inner
            # generator past its own yield and into the 10s sleep.
            task = asyncio.ensure_future(gen.__anext__())
            await asyncio.wait_for(entered_sleep.wait(), timeout=1)
            assert sentinel["resumed"] is True
            assert sentinel["closed"] is False

            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert sentinel["closed"] is True
        assert sentinel.get("resumed_past_sleep") is None
        assert harness.recorded_kwargs["status"] == "ERROR"
        assert harness.recorded_kwargs["error_code"] == "Cancelled"
        assert harness.recorded_kwargs["error_message"] == "Stream cancelled"
        service.execution_service._finalize_turn.assert_not_awaited()
        service.execution_service._finalize_turn.assert_not_awaited()
