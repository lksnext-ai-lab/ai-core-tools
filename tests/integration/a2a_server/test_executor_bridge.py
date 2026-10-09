"""Integration tests for `MattinAgentExecutor` (step_016).

Drives real `A2ARuntime`s (committed test-DB rows, the pinned a2a-sdk store)
through `DefaultRequestHandlerV2.on_message_send`/`on_message_send_stream`
exactly as the real JSON-RPC dispatcher would -- minus the HTTP layer
(step_017's router). `AgentStreamingService.stream_agent_events` is
monkeypatched with scripted async generators (no LLM, per the plan): each
scenario below is a thin `AgentStreamEvent` script plus a `finally`-sentinel
so cancellation tests can prove the *fake stream itself* stopped, not just
that the stored task status says CANCELED (GetTask status alone cannot
prove that -- see the step_002 follow-up this step carries).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

import pytest
from a2a.server.context import ServerCallContext
from a2a.types import a2a_pb2 as pb
from sqlalchemy import func, select

from db.database import SessionLocal
from models.conversation import Conversation, ConversationSource
from services.a2a_server import runtime as runtime_module
from services.a2a_server import visibility_service
from services.a2a_server.executor import MattinAgentExecutor
from services.a2a_server.identity import A2ACallerUser, A2ACallScope, A2ARequestLog, owner_for
from services.a2a_server.sdk_models import get_sdk_models
from services.agent_streaming_service import AgentStreamingService
from tools.streaming_utils import AgentStreamEvent
from utils.a2a_config import get_a2a_config

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Scope/context helpers
# ---------------------------------------------------------------------------


def _build_scope(
    world, *, agent_id: int, key_raw: str, method: str = "SendMessage", app_slug: str | None = None,
) -> A2ACallScope:
    resolve_app_slug = app_slug if app_slug is not None else world.app_slug
    db = SessionLocal()
    try:
        resolution = visibility_service.resolve(db, resolve_app_slug, agent_id, key_raw)
    finally:
        db.close()
    assert resolution.outcome == visibility_service.Outcome.VISIBLE
    key = resolution.key
    assert key is not None
    return A2ACallScope(
        # The resolved snapshot's own `app_id` (rather than guessing from
        # which world attribute the caller passed) keeps this correct for
        # any app the test resolves against.
        app_id=resolution.snapshot.app_id,
        app_slug=resolve_app_slug,
        agent_id=agent_id,
        api_key_id=key.key_id,
        api_key_hash=key.key_hash,
        api_key=key.raw,
        snapshot=resolution.snapshot,
        request_log=A2ARequestLog(method=method),
        base_url="https://a2a.example.test",
    )


def _context_for(scope: A2ACallScope) -> ServerCallContext:
    owner = owner_for(scope.app_id, scope.agent_id, scope.api_key_hash)
    return ServerCallContext(
        user=A2ACallerUser(owner), state={"a2a": scope, "headers": {"a2a-version": "1.0"}}
    )


def _send_request(text: str = "hello", *, return_immediately: bool = False) -> pb.SendMessageRequest:
    return pb.SendMessageRequest(
        message=pb.Message(message_id=str(uuid.uuid4()), role=pb.ROLE_USER, parts=[pb.Part(text=text)]),
        configuration=pb.SendMessageConfiguration(return_immediately=return_immediately),
    )


async def _collect_stream(handler, request, context) -> list:
    events = []
    async for event in handler.on_message_send_stream(request, context):
        events.append(event)
    return events


class _ActiveGlobalRuntime:
    """Registers `rt` as the module-level runtime (`get_runtime()`) for the
    duration of the `with` block, so the bridge's RB-1/RB-14 `track`/`untrack`
    calls land on the same `A2ARuntime` instance the test inspects. Restores
    whatever was registered before (normally `None` outside the lifespan)."""

    def __init__(self, rt) -> None:
        self._rt = rt
        self._previous = None

    def __enter__(self):
        self._previous = runtime_module.get_runtime()
        runtime_module.set_runtime(self._rt)
        return self._rt

    def __exit__(self, *exc_info) -> None:
        runtime_module.set_runtime(self._previous)


def _response_text(task: pb.Task) -> str:
    chunks = []
    for artifact in task.artifacts:
        if artifact.artifact_id != "response":
            continue
        for part in artifact.parts:
            if part.WhichOneof("content") == "text":
                chunks.append(part.text)
    return "".join(chunks)


# ---------------------------------------------------------------------------
# Scripted fakes
# ---------------------------------------------------------------------------


def _happy_path_fake(calls: list, close_state: dict | None = None, gen_holder: dict | None = None):
    async def _stream(
        self, agent_id, message, file_references=None, search_params=None,
        user_context=None, conversation_id=None, db=None,
    ):
        try:
            calls.append(
                {
                    "agent_id": agent_id,
                    "message": message,
                    "user_context": dict(user_context or {}),
                    "conversation_id": conversation_id,
                }
            )
            yield AgentStreamEvent("metadata", {"conversation_id": conversation_id})
            yield AgentStreamEvent("token", {"content": "Hello "})
            yield AgentStreamEvent("token", {"content": "world"})
            yield AgentStreamEvent(
                "done",
                {"response": "Hello world", "conversation_id": conversation_id, "files": []},
                extra={
                    "structured": False,
                    "parsed_response": None,
                    "files_data": [],
                    "conversation_id": conversation_id,
                },
            )
        finally:
            # Only set when the caller cares (item 4): proves the generator
            # was actually torn down via `contextlib.aclosing` -- not left
            # suspended at the `done` yield until the event loop's own,
            # much-later, non-deterministic asyncgen-shutdown hook runs.
            if close_state is not None:
                close_state["closed"] = True

    if gen_holder is None:
        return _stream

    # Captures the *specific* generator object `execute()` ends up driving,
    # so a test can tell "the GC/asyncio finalizer hook ran for *this*
    # generator" apart from "it ran for some unrelated async generator
    # elsewhere in the same scenario" (fix round 1, item 4 mutation check --
    # the naive version of that check was itself vacuous: the hook fires for
    # plenty of other, unrelated generators during a single turn).
    def _stream_capturing(self, *args, **kwargs):
        gen = _stream(self, *args, **kwargs)
        gen_holder["gen"] = gen
        return gen

    return _stream_capturing


def _thinking_flood_fake(state: dict, *, interval_s: float = 0.1, iterations: int = 200):
    """Emits `thinking` every `interval_s` -- events the mapper ignores by
    design (`A2A_STATUS_UPDATES` defaults to false) -- so nothing this
    bridge does in response to them ever reaches `TaskUpdater` (fix round 1,
    item 3's starvation scenario). Never reaches `done` on its own; a
    (remote) cancel is expected to stop it well before `iterations` elapse.
    """
    async def _stream(self, agent_id, message, file_references=None, search_params=None,
                       user_context=None, conversation_id=None, db=None):
        try:
            for i in range(iterations):
                state["count"] = i + 1
                yield AgentStreamEvent("thinking", {"message": "..."})
                await asyncio.sleep(interval_s)
            state["completed_normally"] = True  # pragma: no cover - cancel expected first
        finally:
            state["stopped"] = True

    return _stream


def _hangs_fake(state: dict, *, hang_seconds: float):
    """Yields one token, then hangs well past any reasonable turn timeout."""
    async def _stream(self, agent_id, message, file_references=None, search_params=None,
                       user_context=None, conversation_id=None, db=None):
        try:
            yield AgentStreamEvent("token", {"content": "stuck"})
            await asyncio.sleep(hang_seconds)
            state["finished_without_timeout"] = True  # pragma: no cover - timeout expected first
        finally:
            state["stopped"] = True

    return _stream


def _input_error_fake(calls: list):
    async def _stream(self, agent_id, message, file_references=None, search_params=None,
                       user_context=None, conversation_id=None, db=None):
        calls.append(True)
        return
        yield  # pragma: no cover - never reached; keeps this an async generator

    return _stream


_SECRET_EXCEPTION_TEXT = "super secret internal stack trace detail"


def _raising_fake(calls: list):
    async def _stream(self, agent_id, message, file_references=None, search_params=None,
                       user_context=None, conversation_id=None, db=None):
        calls.append(True)
        yield AgentStreamEvent("metadata", {"conversation_id": conversation_id})
        raise RuntimeError(_SECRET_EXCEPTION_TEXT)

    return _stream


def _unrelated_timeout_error_fake(calls: list):
    """Raises a plain builtin `TimeoutError` that has nothing to do with
    `A2A_TURN_MAX_SECONDS` (fix round 2, item 3's scenario -- e.g. an HTTP
    client or DB driver timing out deep inside a real agent chain)."""
    async def _stream(self, agent_id, message, file_references=None, search_params=None,
                       user_context=None, conversation_id=None, db=None):
        calls.append(True)
        yield AgentStreamEvent("metadata", {"conversation_id": conversation_id})
        raise TimeoutError("some unrelated downstream timeout, not ours")

    return _stream


def _slow_fake(state: dict, *, chunks: int = 100, delay_s: float = 0.05):
    async def _stream(self, agent_id, message, file_references=None, search_params=None,
                       user_context=None, conversation_id=None, db=None):
        try:
            for i in range(chunks):
                state["count"] = i + 1
                yield AgentStreamEvent("token", {"content": "x"})
                await asyncio.sleep(delay_s)
            state["completed_normally"] = True
            yield AgentStreamEvent(
                "done",
                {"response": "x" * chunks, "conversation_id": conversation_id},
                extra={
                    "structured": False, "parsed_response": None,
                    "files_data": [], "conversation_id": conversation_id,
                },
            )
        finally:
            # The finally-sentinel (step_002 follow-up): proves the *generator
            # itself* was torn down by cancellation, not merely that the
            # stored task status says CANCELED.
            state["stopped"] = True

    return _stream


def _silent_fake(state: dict, *, silent_seconds: float):
    async def _stream(self, agent_id, message, file_references=None, search_params=None,
                       user_context=None, conversation_id=None, db=None):
        try:
            yield AgentStreamEvent("token", {"content": "start"})
            await asyncio.sleep(silent_seconds)
            state["finished_without_cancel"] = True
            yield AgentStreamEvent(
                "done",
                {"response": "start-done", "conversation_id": conversation_id},
                extra={
                    "structured": False, "parsed_response": None,
                    "files_data": [], "conversation_id": conversation_id,
                },
            )
        finally:
            state["stopped"] = True

    return _stream


# ---------------------------------------------------------------------------
# AC-14 / AC-15 / AC-16 / AC-44 (caller type): happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_send_completes_with_conversation_and_caller_type(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        calls: list = []
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _happy_path_fake(calls))

        world = a2a_committed_world
        rt = a2a_runtime_factory(MattinAgentExecutor())
        scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
        context = _context_for(scope)

        with _ActiveGlobalRuntime(rt):
            result = asyncio.run(rt.handler.on_message_send(_send_request("hi"), context))

        assert isinstance(result, pb.Task)
        assert result.status.state == pb.TaskState.TASK_STATE_COMPLETED
        assert _response_text(result) == "Hello world"

        # AC-14: contextId is server-generated (the request supplied none).
        assert result.context_id
        assert len(result.context_id) <= 36

        assert len(calls) == 1
        assert calls[0]["user_context"]["caller_type_override"] == "A2A"
        conversation_id = calls[0]["conversation_id"]
        assert conversation_id is not None

        db = SessionLocal()
        try:
            conversation = db.get(Conversation, conversation_id)
            assert conversation is not None
            assert conversation.source == ConversationSource.A2A
            assert conversation.api_key_hash == scope.api_key_hash
        finally:
            db.close()

        # RB-1/RB-14: the completed turn must not linger in `in_flight`.
        assert not rt.in_flight
        # Fix round 1, item 7: the request log's outcome for a completed turn.
        assert scope.request_log.outcome == "completed"

    def test_generator_is_closed_via_aclosing_not_left_for_gc(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        """Fix round 1, item 4: proves `execute()` itself explicitly closes
        the fake stream generator (via `contextlib.aclosing`) -- not that it
        merely *ends up* closed one way or another.

        A bare "was it closed within 2s" check is not actually sensitive to
        removing `aclosing`: CPython closes an abandoned async generator as
        soon as its refcount hits zero, via the loop's own asyncgen
        finalizer hook (`sys.set_asyncgen_hooks`) -- which, in this test,
        fires almost immediately once `execute()`'s local `events` reference
        goes out of scope, regardless of whether `execute()` called
        `aclose()` itself. (Confirmed experimentally, fix round 1: swapping
        `contextlib.aclosing` for a no-op `contextlib.nullcontext` here still
        left the bare "closed within 2s" check green.)

        So this test additionally overrides the *running* loop's asyncgen
        finalizer hook with a spy for the duration of the scenario, and
        checks it specifically against *this fake's own* generator object
        (`gen_holder`) -- a plain "did the hook fire at all" check is itself
        a false positive, since plenty of unrelated async generators get
        GC'd during any one turn (confirmed experimentally too). Only an
        *explicit* `aclose()` call (what `contextlib.aclosing.__aexit__`
        does) closes our generator without that hook ever seeing it.
        """
        calls: list = []
        close_state = {"closed": False}
        gen_holder: dict = {}
        monkeypatch.setattr(
            AgentStreamingService,
            "stream_agent_events",
            _happy_path_fake(calls, close_state, gen_holder),
        )

        world = a2a_committed_world
        rt = a2a_runtime_factory(MattinAgentExecutor())
        scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
        context = _context_for(scope)

        async def _scenario():
            import sys

            original_firstiter, original_finalizer = sys.get_asyncgen_hooks()
            finalizer_spy = {"triggered": False}

            def _spy_finalizer(agen):
                if agen is gen_holder.get("gen"):
                    finalizer_spy["triggered"] = True
                if original_finalizer is not None:
                    original_finalizer(agen)

            sys.set_asyncgen_hooks(firstiter=original_firstiter, finalizer=_spy_finalizer)
            try:
                result = await rt.handler.on_message_send(_send_request("hi"), context)
                start = time.monotonic()
                while not close_state["closed"] and time.monotonic() - start < 2.0:
                    await asyncio.sleep(0.02)
                elapsed = time.monotonic() - start
                assert close_state["closed"] is True, (
                    f"fake stream generator was not closed within 2s of task completion "
                    f"(elapsed={elapsed:.3f}s) -- execute() must wrap it in contextlib.aclosing"
                )
                assert elapsed < 2.0
                assert gen_holder.get("gen") is not None, "the fake generator was never captured"
                assert finalizer_spy["triggered"] is False, (
                    "the fake generator was torn down via the asyncio/GC finalizer hook, "
                    "not an explicit aclose() call -- execute() must close it itself "
                    "(contextlib.aclosing), not rely on garbage collection"
                )
            finally:
                sys.set_asyncgen_hooks(firstiter=original_firstiter, finalizer=original_finalizer)
            return result

        with _ActiveGlobalRuntime(rt):
            result = asyncio.run(_scenario())

        assert result.status.state == pb.TaskState.TASK_STATE_COMPLETED

    def test_streaming_order_is_task_working_artifacts_then_completed(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        calls: list = []
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _happy_path_fake(calls))

        world = a2a_committed_world
        rt = a2a_runtime_factory(MattinAgentExecutor())
        scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
        context = _context_for(scope)

        with _ActiveGlobalRuntime(rt):
            events = asyncio.run(_collect_stream(rt.handler, _send_request("hi"), context))

        assert isinstance(events[0], pb.Task)
        assert events[0].status.state == pb.TaskState.TASK_STATE_SUBMITTED

        assert isinstance(events[1], pb.TaskStatusUpdateEvent)
        assert events[1].status.state == pb.TaskState.TASK_STATE_WORKING

        artifact_events = [e for e in events[2:-1] if isinstance(e, pb.TaskArtifactUpdateEvent)]
        assert artifact_events, "expected at least one artifact update between WORKING and COMPLETED"
        # The SDK requires the artifact's very first chunk to use append=False
        # (it is what *creates* the artifact); every later chunk of the same
        # artifact must then use append=True (task_manager.py's
        # `append_artifact_to_task`).
        assert artifact_events[0].append is False
        assert all(e.append for e in artifact_events[1:])

        assert isinstance(events[-1], pb.TaskStatusUpdateEvent)
        assert events[-1].status.state == pb.TaskState.TASK_STATE_COMPLETED

        # AC-16: `input_required` is never one of the states observed.
        for event in events:
            if isinstance(event, (pb.Task, pb.TaskStatusUpdateEvent)):
                assert event.status.state != pb.TaskState.TASK_STATE_INPUT_REQUIRED

    def test_return_immediately_returns_promptly_then_get_task_shows_completed(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        calls: list = []
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _happy_path_fake(calls))

        world = a2a_committed_world
        rt = a2a_runtime_factory(MattinAgentExecutor())
        scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
        context = _context_for(scope)

        async def _scenario():
            initial = await rt.handler.on_message_send(_send_request("hi", return_immediately=True), context)
            await asyncio.sleep(0.3)
            final = await rt.handler.on_get_task(pb.GetTaskRequest(id=initial.id), context)
            return initial, final

        with _ActiveGlobalRuntime(rt):
            initial, final = asyncio.run(_scenario())

        assert isinstance(initial, pb.Task)
        assert initial.status.state not in (
            pb.TaskState.TASK_STATE_COMPLETED,
            pb.TaskState.TASK_STATE_FAILED,
            pb.TaskState.TASK_STATE_CANCELED,
        )
        assert final.status.state == pb.TaskState.TASK_STATE_COMPLETED
        assert _response_text(final) == "Hello world"


# ---------------------------------------------------------------------------
# AC-24: generic failure, no leaked exception text
# ---------------------------------------------------------------------------


class TestFailure:
    def test_unexpected_exception_fails_generically(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        calls: list = []
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _raising_fake(calls))

        world = a2a_committed_world
        rt = a2a_runtime_factory(MattinAgentExecutor())
        scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
        context = _context_for(scope)

        with _ActiveGlobalRuntime(rt):
            result = asyncio.run(rt.handler.on_message_send(_send_request("hi"), context))

        assert result.status.state == pb.TaskState.TASK_STATE_FAILED
        message_text = "".join(
            part.text for part in result.status.message.parts if part.WhichOneof("content") == "text"
        )
        assert message_text == "Agent execution failed."
        assert _SECRET_EXCEPTION_TEXT not in message_text

        # Also check the raw stored row, not just the in-memory returned Task.
        models = get_sdk_models()
        db = SessionLocal()
        try:
            stored = db.get(models.task, result.id)
            assert stored is not None
            assert _SECRET_EXCEPTION_TEXT not in str(stored.status)
        finally:
            db.close()

        assert not rt.in_flight
        assert scope.request_log.outcome == "failed"


# ---------------------------------------------------------------------------
# Input errors: failed naming the part, stream_agent_events never called
# ---------------------------------------------------------------------------


class TestInputError:
    def test_bad_file_part_fails_without_ever_streaming(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        calls: list = []
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _input_error_fake(calls))

        world = a2a_committed_world
        rt = a2a_runtime_factory(MattinAgentExecutor())
        scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
        context = _context_for(scope)

        # A FilePart whose URI resolves to a blocked (loopback) address: this
        # passes the SDK-level `A2ARequestContextBuilder` validation (it only
        # checks the url's scheme/length, not SSRF), so it reaches
        # `input_service.build_turn_inputs`, which rejects it via the shared
        # SSRF guard -- failing the turn before any streaming starts.
        request = pb.SendMessageRequest(
            message=pb.Message(
                message_id=str(uuid.uuid4()),
                role=pb.ROLE_USER,
                parts=[
                    pb.Part(text="hi"),
                    pb.Part(url="http://127.0.0.1/secret", filename="broken.bin"),
                ],
            )
        )

        with _ActiveGlobalRuntime(rt):
            result = asyncio.run(rt.handler.on_message_send(request, context))

        assert result.status.state == pb.TaskState.TASK_STATE_FAILED
        message_text = "".join(
            part.text for part in result.status.message.parts if part.WhichOneof("content") == "text"
        )
        assert "part 2" in message_text
        assert calls == []  # stream_agent_events was never reached
        assert not rt.in_flight
        assert scope.request_log.outcome == "input_error"


# ---------------------------------------------------------------------------
# Cross-tenant: an inconsistent (app, agent) scope must never bind or stream
# ---------------------------------------------------------------------------


class TestCrossTenantScope:
    def test_agent_of_another_app_fails_generically_without_binding_or_streaming(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        """Fix round 1, item 9: a scope whose `app_id` and `agent_id` belong
        to *different* apps (something a correct router/visibility
        resolution should never produce, but this bridge must not trust
        blindly) must fail generically, before `bind_context` creates a
        Conversation/link row and before `stream_agent_events` is ever
        called -- `context_binding_service._load_scoped_agent` (step_013)
        is the actual enforcement point; this pins the bridge's behavior
        when that check fires.
        """
        calls: list = []
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _happy_path_fake(calls))

        world = a2a_committed_world
        rt = a2a_runtime_factory(MattinAgentExecutor())
        # A valid key of `other_app_id`, but `agent_public_id` belongs to
        # `app_id` -- an inconsistent (app, agent) pair.
        other_app_scope = _build_scope(
            world, agent_id=world.other_agent_id, key_raw=world.other_key_raw,
            app_slug=world.other_app_slug,
        )
        mismatched_scope = A2ACallScope(
            app_id=other_app_scope.app_id,
            app_slug=other_app_scope.app_slug,
            agent_id=world.agent_public_id,
            api_key_id=other_app_scope.api_key_id,
            api_key_hash=other_app_scope.api_key_hash,
            api_key=other_app_scope.api_key,
            snapshot=other_app_scope.snapshot,
            request_log=A2ARequestLog(method="SendMessage"),
            base_url=other_app_scope.base_url,
        )
        context = _context_for(mismatched_scope)

        def _conversation_count() -> int:
            db = SessionLocal()
            try:
                return db.execute(
                    select(func.count())
                    .select_from(Conversation)
                    .where(Conversation.agent_id == world.agent_public_id)
                ).scalar()
            finally:
                db.close()

        conversation_count_before = _conversation_count()

        with _ActiveGlobalRuntime(rt):
            result = asyncio.run(rt.handler.on_message_send(_send_request("hi"), context))

        assert result.status.state == pb.TaskState.TASK_STATE_FAILED
        message_text = "".join(
            part.text for part in result.status.message.parts if part.WhichOneof("content") == "text"
        )
        assert message_text == "Agent execution failed."
        assert calls == []  # stream_agent_events was never reached
        assert _conversation_count() == conversation_count_before

        assert not rt.in_flight
        assert mismatched_scope.request_log.outcome == "failed"


# ---------------------------------------------------------------------------
# AC-34: cancellation (local and remote), with a finally-sentinel proof
# ---------------------------------------------------------------------------


class TestCancellation:
    def test_local_cancel_stops_the_fake_stream_within_two_seconds(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        state = {"count": 0, "stopped": False, "completed_normally": False}
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _slow_fake(state))

        world = a2a_committed_world
        rt = a2a_runtime_factory(MattinAgentExecutor())
        scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
        context = _context_for(scope)

        async def _scenario():
            initial = await rt.handler.on_message_send(_send_request("hi", return_immediately=True), context)
            await asyncio.sleep(0.2)
            in_flight_mid_stream = (owner_for(scope.app_id, scope.agent_id, scope.api_key_hash), initial.id) in rt.in_flight
            cancel_result = await rt.handler.on_cancel_task(pb.CancelTaskRequest(id=initial.id), context)
            start = time.monotonic()
            while not state["stopped"] and time.monotonic() - start < 2.0:
                await asyncio.sleep(0.05)
            elapsed = time.monotonic() - start
            # Fix round 1, item 4: assert *inside* the running scenario, before
            # `asyncio.run()` returns -- otherwise a stuck generator could get
            # silently swept up by the event loop's own (unbounded, mechanism-
            # independent) asyncgen-shutdown hook at teardown, making an
            # out-of-loop assertion pass vacuously regardless of whether our
            # own cancellation plumbing (or the 2s bound) actually held.
            assert state["stopped"] is True, (
                f"fake generator not stopped within 2s of local cancel (elapsed={elapsed:.3f}s)"
            )
            assert elapsed < 2.0
            return initial, cancel_result, in_flight_mid_stream

        with _ActiveGlobalRuntime(rt):
            initial, cancel_result, in_flight_mid_stream = asyncio.run(_scenario())

        assert in_flight_mid_stream, "the turn should have been tracked in rt.in_flight while streaming"
        assert cancel_result.status.state == pb.TaskState.TASK_STATE_CANCELED
        assert state["completed_normally"] is False
        assert not rt.in_flight
        assert scope.request_log.outcome == "canceled"

        final = asyncio.run(rt.handler.on_get_task(pb.GetTaskRequest(id=initial.id), context))
        assert final.status.state == pb.TaskState.TASK_STATE_CANCELED

    def test_remote_cancel_on_another_worker_stops_the_fake_stream(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        state = {"count": 0, "stopped": False, "completed_normally": False}
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _slow_fake(state))

        world = a2a_committed_world
        rt_a = a2a_runtime_factory(MattinAgentExecutor())
        rt_b = a2a_runtime_factory(MattinAgentExecutor())
        scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
        context = _context_for(scope)

        async def _scenario():
            initial = await rt_a.handler.on_message_send(
                _send_request("hi", return_immediately=True), context
            )
            await asyncio.sleep(0.2)
            cancel_result = await rt_b.handler.on_cancel_task(pb.CancelTaskRequest(id=initial.id), context)
            start = time.monotonic()
            while not state["stopped"] and time.monotonic() - start < 2.0:
                await asyncio.sleep(0.05)
            elapsed = time.monotonic() - start
            assert state["stopped"] is True, (
                f"remote cancel did not stop worker A's producer within 2s (elapsed={elapsed:.3f}s)"
            )
            assert elapsed < 2.0
            return initial, cancel_result

        with _ActiveGlobalRuntime(rt_a):
            initial, cancel_result = asyncio.run(_scenario())

        assert cancel_result.status.state == pb.TaskState.TASK_STATE_CANCELED
        assert state["completed_normally"] is False
        assert not rt_a.in_flight
        assert scope.request_log.outcome == "canceled"

    def test_remote_cancel_during_silence_is_bounded_by_keepalive(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        get_a2a_config.cache_clear()
        monkeypatch.setenv("A2A_KEEPALIVE_SECONDS", "0.3")
        get_a2a_config.cache_clear()
        try:
            state = {"stopped": False, "finished_without_cancel": False}
            monkeypatch.setattr(
                AgentStreamingService, "stream_agent_events", _silent_fake(state, silent_seconds=5.0)
            )

            world = a2a_committed_world
            rt_a = a2a_runtime_factory(MattinAgentExecutor())
            rt_b = a2a_runtime_factory(MattinAgentExecutor())
            scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
            context = _context_for(scope)

            async def _scenario():
                initial = await rt_a.handler.on_message_send(
                    _send_request("hi", return_immediately=True), context
                )
                # Let at least one keepalive tick land (refreshing last_updated)
                # before the remote cancel is issued.
                await asyncio.sleep(0.5)
                cancel_result = await rt_b.handler.on_cancel_task(
                    pb.CancelTaskRequest(id=initial.id), context
                )
                start = time.monotonic()
                while not state["stopped"] and time.monotonic() - start < 2.0:
                    await asyncio.sleep(0.05)
                elapsed = time.monotonic() - start
                assert state["stopped"] is True, (
                    f"remote cancel during silence did not stop the producer within "
                    f"2s (elapsed={elapsed:.3f}s)"
                )
                assert elapsed < 2.0
                return cancel_result

            with _ActiveGlobalRuntime(rt_a):
                cancel_result = asyncio.run(_scenario())

            assert cancel_result.status.state == pb.TaskState.TASK_STATE_CANCELED
            assert state["finished_without_cancel"] is False
            assert scope.request_log.outcome == "canceled"
        finally:
            monkeypatch.delenv("A2A_KEEPALIVE_SECONDS", raising=False)
            get_a2a_config.cache_clear()

    def test_remote_cancel_survives_a_flood_of_ignored_events(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        """Fix round 1, item 3: a fake emitting `thinking` every 0.1s --
        events the mapper ignores by default (`A2A_STATUS_UPDATES=false`),
        so nothing this bridge does in response to them ever reaches
        `TaskUpdater` -- must not starve the keepalive. Before the fix,
        `_drain`'s keepalive branch only ran when *no* event arrived within
        the poll window; a steady stream of ignored events kept the
        event-arrival branch busy instead, so `last_updated` was never
        refreshed and the remote cancel's version-conflict detection never
        got a chance to fire within any reasonable bound.
        """
        get_a2a_config.cache_clear()
        monkeypatch.setenv("A2A_KEEPALIVE_SECONDS", "0.3")
        get_a2a_config.cache_clear()
        try:
            state = {"count": 0, "stopped": False, "completed_normally": False}
            monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _thinking_flood_fake(state))

            world = a2a_committed_world
            rt_a = a2a_runtime_factory(MattinAgentExecutor())
            rt_b = a2a_runtime_factory(MattinAgentExecutor())
            scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
            context = _context_for(scope)

            async def _scenario():
                initial = await rt_a.handler.on_message_send(
                    _send_request("hi", return_immediately=True), context
                )
                await asyncio.sleep(0.5)
                cancel_result = await rt_b.handler.on_cancel_task(
                    pb.CancelTaskRequest(id=initial.id), context
                )
                start = time.monotonic()
                while not state["stopped"] and time.monotonic() - start < 2.0:
                    await asyncio.sleep(0.05)
                elapsed = time.monotonic() - start
                assert state["stopped"] is True, (
                    f"remote cancel did not stop the thinking-flood producer within "
                    f"2s (elapsed={elapsed:.3f}s) -- keepalive starvation regression"
                )
                assert elapsed < 2.0
                return cancel_result

            with _ActiveGlobalRuntime(rt_a):
                cancel_result = asyncio.run(_scenario())

            assert cancel_result.status.state == pb.TaskState.TASK_STATE_CANCELED
            assert state["completed_normally"] is False
        finally:
            monkeypatch.delenv("A2A_KEEPALIVE_SECONDS", raising=False)
            get_a2a_config.cache_clear()


# ---------------------------------------------------------------------------
# RB-2 (bridge side): a hard wall-clock cap on the whole streaming section
# ---------------------------------------------------------------------------


class TestTurnTimeout:
    def test_a_hung_stream_is_failed_as_a_timeout(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        get_a2a_config.cache_clear()
        monkeypatch.setenv("A2A_TURN_MAX_SECONDS", "1")
        get_a2a_config.cache_clear()
        try:
            state = {"stopped": False, "finished_without_timeout": False}
            monkeypatch.setattr(
                AgentStreamingService, "stream_agent_events", _hangs_fake(state, hang_seconds=30.0)
            )

            world = a2a_committed_world
            rt = a2a_runtime_factory(MattinAgentExecutor())
            scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
            context = _context_for(scope)

            async def _scenario():
                start = time.monotonic()
                result = await rt.handler.on_message_send(_send_request("hi"), context)
                elapsed = time.monotonic() - start
                assert elapsed < 5.0, f"timeout took too long to fire (elapsed={elapsed:.3f}s)"
                assert state["stopped"] is True, "the hung generator must be torn down on timeout"
                return result

            with _ActiveGlobalRuntime(rt):
                result = asyncio.run(_scenario())

            assert result.status.state == pb.TaskState.TASK_STATE_FAILED
            message_text = "".join(
                part.text for part in result.status.message.parts if part.WhichOneof("content") == "text"
            )
            assert message_text == "Agent execution timed out."
            assert state["finished_without_timeout"] is False
            assert scope.request_log.outcome == "timeout"
            assert not rt.in_flight
        finally:
            monkeypatch.delenv("A2A_TURN_MAX_SECONDS", raising=False)
            get_a2a_config.cache_clear()

    def test_an_unrelated_timeout_error_is_not_mislabeled_as_a_turn_timeout(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        """Fix round 2, item 3: a plain builtin `TimeoutError` raised by the
        stream for a reason that has nothing to do with `A2A_TURN_MAX_SECONDS`
        must fall through to the generic failure path (`"Agent execution
        failed."`), not be mislabeled `"Agent execution timed out."` just
        because `except TimeoutError:` would otherwise catch it too. Uses the
        default `A2A_TURN_MAX_SECONDS` (900s), so the bridge's own deadline
        never comes close to firing during this test.
        """
        calls: list = []
        monkeypatch.setattr(
            AgentStreamingService, "stream_agent_events", _unrelated_timeout_error_fake(calls)
        )

        world = a2a_committed_world
        rt = a2a_runtime_factory(MattinAgentExecutor())
        scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
        context = _context_for(scope)

        with _ActiveGlobalRuntime(rt):
            result = asyncio.run(rt.handler.on_message_send(_send_request("hi"), context))

        assert result.status.state == pb.TaskState.TASK_STATE_FAILED
        message_text = "".join(
            part.text for part in result.status.message.parts if part.WhichOneof("content") == "text"
        )
        assert message_text == "Agent execution failed."
        assert message_text != "Agent execution timed out."
        assert scope.request_log.outcome == "failed"
        assert not rt.in_flight


# ---------------------------------------------------------------------------
# AC-16 / AC-15 source-level proofs (no `input_required`, no SSE parsing)
# ---------------------------------------------------------------------------


class TestSourceLevelInvariants:
    def test_executor_never_references_input_required(self):
        import services.a2a_server.executor as module

        text = Path(module.__file__).read_text()
        assert "requires_input" not in text
        assert "INPUT_REQUIRED" not in text

    def test_executor_never_parses_sse(self):
        import services.a2a_server.executor as module

        text = Path(module.__file__).read_text()
        # The module docstring *talks about* format_sse_event (to explain why
        # it is absent); the one thing that must never appear is an actual
        # import of it, or an SSE wire-format literal.
        assert "import format_sse_event" not in text
        assert "streaming_utils import format_sse_event" not in text
        assert "data: {payload}" not in text
        assert 'f"data: ' not in text


# ---------------------------------------------------------------------------
# Unit-level: the bridge opens and closes its own session, never a request one
# ---------------------------------------------------------------------------


def _patch_tracking_session_local(monkeypatch) -> tuple[list, list]:
    """Patches `services.a2a_server.executor.SessionLocal` to record every
    session it opens and whether `close()` was later called on it. Returns
    `(opened, closed_flags)`, parallel lists."""
    opened: list = []
    closed_flags: list = []
    real_session_local = SessionLocal

    def _tracking_session_local(*args, **kwargs):
        session = real_session_local(*args, **kwargs)
        opened.append(session)
        flag = {"closed": False}
        closed_flags.append(flag)
        real_close = session.close

        def _tracking_close():
            flag["closed"] = True
            return real_close()

        session.close = _tracking_close
        return session

    monkeypatch.setattr("services.a2a_server.executor.SessionLocal", _tracking_session_local)
    return opened, closed_flags


class TestSessionHygiene:
    """Fix round 1, item 11: parametrized over every path that reaches
    `db = SessionLocal()` -- happy, input error, an unexpected raise, and a
    cancellation -- not just the happy path."""

    def test_happy_path_session_local_is_opened_and_closed_once_per_turn(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        calls: list = []
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _happy_path_fake(calls))
        opened, closed_flags = _patch_tracking_session_local(monkeypatch)

        world = a2a_committed_world
        rt = a2a_runtime_factory(MattinAgentExecutor())
        scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
        context = _context_for(scope)

        with _ActiveGlobalRuntime(rt):
            result = asyncio.run(rt.handler.on_message_send(_send_request("hi"), context))

        assert result.status.state == pb.TaskState.TASK_STATE_COMPLETED
        assert len(opened) == 1, "the bridge must open exactly one SessionLocal() per turn"
        assert closed_flags[0]["closed"] is True, "the bridge must close its own session in `finally`"

    def test_input_error_session_local_is_opened_and_closed_once_per_turn(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        calls: list = []
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _input_error_fake(calls))
        opened, closed_flags = _patch_tracking_session_local(monkeypatch)

        world = a2a_committed_world
        rt = a2a_runtime_factory(MattinAgentExecutor())
        scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
        context = _context_for(scope)
        request = pb.SendMessageRequest(
            message=pb.Message(
                message_id=str(uuid.uuid4()),
                role=pb.ROLE_USER,
                parts=[
                    pb.Part(text="hi"),
                    pb.Part(url="http://127.0.0.1/secret", filename="broken.bin"),
                ],
            )
        )

        with _ActiveGlobalRuntime(rt):
            result = asyncio.run(rt.handler.on_message_send(request, context))

        assert result.status.state == pb.TaskState.TASK_STATE_FAILED
        # `bind_context` already opened/used this same session before the
        # input error fired -- `SessionLocal()` must still have been called
        # exactly once for the whole turn.
        assert len(opened) == 1
        assert closed_flags[0]["closed"] is True

    def test_raising_fake_session_local_is_opened_and_closed_once_per_turn(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        calls: list = []
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _raising_fake(calls))
        opened, closed_flags = _patch_tracking_session_local(monkeypatch)

        world = a2a_committed_world
        rt = a2a_runtime_factory(MattinAgentExecutor())
        scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
        context = _context_for(scope)

        with _ActiveGlobalRuntime(rt):
            result = asyncio.run(rt.handler.on_message_send(_send_request("hi"), context))

        assert result.status.state == pb.TaskState.TASK_STATE_FAILED
        assert len(opened) == 1
        assert closed_flags[0]["closed"] is True

    def test_cancelled_turn_session_local_is_opened_and_closed_once_per_turn(
        self, a2a_committed_world, a2a_runtime_factory, monkeypatch
    ):
        state = {"count": 0, "stopped": False, "completed_normally": False}
        monkeypatch.setattr(AgentStreamingService, "stream_agent_events", _slow_fake(state))
        opened, closed_flags = _patch_tracking_session_local(monkeypatch)

        world = a2a_committed_world
        rt = a2a_runtime_factory(MattinAgentExecutor())
        scope = _build_scope(world, agent_id=world.agent_public_id, key_raw=world.key_1_raw)
        context = _context_for(scope)

        async def _scenario():
            initial = await rt.handler.on_message_send(_send_request("hi", return_immediately=True), context)
            await asyncio.sleep(0.2)
            cancel_result = await rt.handler.on_cancel_task(pb.CancelTaskRequest(id=initial.id), context)
            start = time.monotonic()
            while not state["stopped"] and time.monotonic() - start < 2.0:
                await asyncio.sleep(0.05)
            assert state["stopped"] is True
            return cancel_result

        with _ActiveGlobalRuntime(rt):
            cancel_result = asyncio.run(_scenario())

        assert cancel_result.status.state == pb.TaskState.TASK_STATE_CANCELED
        assert len(opened) == 1
        assert closed_flags[0]["closed"] is True
