"""Behavioural half of the a2a-sdk contract suite for `services/a2a_server` (AD-2, AD-6).

**Why this suite exists.** `a2a-sdk==1.2.2` is exact-pinned because
`storage.py` writes three private attributes
(`store._event_model`, `store._version_model`, `stream._event_model`) and
relies on the meaning of one public one (`store.as_task_store.task_model`). A
patch release could rename or repurpose any of them. This suite is the gate
that must pass again before the pin is ever bumped (see the comment above
the `a2a-sdk` line in `pyproject.toml`).

Every assertion message says: "a2a-sdk contract changed; review
services/a2a_server/storage.py before bumping the pin" so a failure points
straight at the file to review.

This file runs against the real test DB (port 5433) with `build_bound_storage`,
and proves AD-6's cancellation design end-to-end: local cancel, remote
cancel, remote cancel during silence with vs. without keepalives, and owner
isolation (AD-2/FR-15). The static (no-DB) half -- SDK shape/version checks
-- lives in `tests/unit/services/a2a_server/test_sdk_contract_static.py`.
"""

from __future__ import annotations

import asyncio
import gc
import time
import uuid
from contextlib import suppress

import pytest
import sqlalchemy as sa
from a2a.auth.user import User
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.context import ServerCallContext
from a2a.server.request_handlers.default_request_handler_v2 import (
    DefaultRequestHandlerV2,
)
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import a2a_pb2 as pb
from a2a.utils.errors import (
    InvalidParamsError,
    TaskNotCancelableError,
    TaskNotFoundError,
    UnsupportedOperationError,
)
from services.a2a_server.sdk_models import get_sdk_models
from services.a2a_server.storage import build_bound_storage

_CONTRACT_MSG = (
    "a2a-sdk contract changed; review services/a2a_server/storage.py before bumping the pin"
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


class _StaticUser(User):
    """Minimal `a2a.auth.user.User` for tests: a fixed, authenticated owner."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def user_name(self) -> str:
        return self._name


def _ctx(owner: str) -> ServerCallContext:
    return ServerCallContext(
        user=_StaticUser(owner),
        state={"headers": {"a2a-version": "1.0"}},
    )


def _resolve_owner_from_context(context: ServerCallContext) -> str:
    """The `owner_resolver` every test passes to `build_bound_storage`.

    Equivalent to the SDK's own default (`resolve_user_scope`), but supplied
    explicitly: `owner_resolver` has no default any more (AC-32 fix round) --
    every caller, including tests, must say so. All owner strings this suite
    constructs are prefixed `"a2a:"` (`_owner_prefix` below) to satisfy the
    fail-closed check in `storage._fail_closed_owner_resolver`.
    """
    return context.user.user_name


def _send_request(*, text: str = "hello", return_immediately: bool = False) -> pb.SendMessageRequest:
    return pb.SendMessageRequest(
        message=pb.Message(
            message_id=str(uuid.uuid4()),
            role=pb.ROLE_USER,
            parts=[pb.Part(text=text)],
        ),
        configuration=pb.SendMessageConfiguration(return_immediately=return_immediately),
    )


class _CountingToyExecutor(AgentExecutor):
    """Toy `AgentExecutor` for the behavioural contract (plan step_002.6).

    Enqueues an initial `Task` if none exists, starts work, then either:
      - streams `num_chunks` artifact chunks `chunk_delay_s` apart, incrementing
        `counter["n"]` before each one, or
      - stays silent for `silent_duration_s`, optionally emitting a
        `update_status(WORKING)` keepalive every `keepalive_interval_s` (AD-6).
    Ends with `complete()`. `cancel()` is best-effort, mirroring AD-8.

    `counter` doubles as a progress/observation channel for tests: besides
    `"n"` (chunk counter), both branches record `"cancelled_at"` (the
    absolute `time.monotonic()` reading when the `asyncio.CancelledError`
    that interrupted the loop/wait was observed -- i.e. when the producer
    actually stopped) or `"completed_at"` (same clock, if the loop/wait ran
    to completion uncancelled). This is deliberately **not** `GetTask`'s
    status: `DefaultRequestHandlerV2._cancel_remote` writes `CANCELED` to the
    task row synchronously, before the owning worker's producer ever notices
    (AD-6) -- so `GetTask` already reads `CANCELED` immediately on *any*
    remote cancel, keepalives or not, and cannot be used to tell whether, or
    how fast, the producer itself actually stopped. Only the producer's own
    cancellation timing (`"cancelled_at"`) can -- that is the signal every
    cancel test in this suite waits on before sampling anything else, so that
    a chunk that was already in flight when `CancelTask` returned (AD-6: the
    delay is "until the next save") is never mistaken for cancellation
    failing.
    """

    def __init__(
        self,
        *,
        counter: dict[str, float] | None = None,
        num_chunks: int = 0,
        chunk_delay_s: float = 0.0,
        silent_duration_s: float | None = None,
        keepalive_interval_s: float | None = None,
    ) -> None:
        self._counter = counter if counter is not None else {"n": 0}
        self._num_chunks = num_chunks
        self._chunk_delay_s = chunk_delay_s
        self._silent_duration_s = silent_duration_s
        self._keepalive_interval_s = keepalive_interval_s

    async def execute(self, context, event_queue) -> None:
        if context.current_task is None:
            message = context.message
            initial = pb.Task(
                id=context.task_id,
                context_id=context.context_id,
                status=pb.TaskStatus(state=pb.TaskState.TASK_STATE_SUBMITTED),
                history=[message] if message is not None else [],
            )
            await event_queue.enqueue_event(initial)

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()

        if self._silent_duration_s is not None:
            try:
                elapsed = 0.0
                step = self._keepalive_interval_s or self._silent_duration_s
                while elapsed < self._silent_duration_s:
                    await asyncio.sleep(step)
                    elapsed += step
                    if self._keepalive_interval_s is not None:
                        await updater.update_status(pb.TaskState.TASK_STATE_WORKING)
            except asyncio.CancelledError:
                self._counter["cancelled_at"] = time.monotonic()
                raise
            self._counter["completed_at"] = time.monotonic()
        else:
            try:
                for i in range(self._num_chunks):
                    await asyncio.sleep(self._chunk_delay_s)
                    self._counter["n"] += 1
                    await updater.add_artifact(
                        [pb.Part(text=f"chunk-{i}")],
                        artifact_id="artifact-1",
                        append=i > 0,
                    )
            except asyncio.CancelledError:
                self._counter["cancelled_at"] = time.monotonic()
                raise
            self._counter["completed_at"] = time.monotonic()

        await updater.complete()

    async def cancel(self, context, event_queue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        with suppress(Exception):
            await updater.cancel()


def _agent_card() -> pb.AgentCard:
    return pb.AgentCard(
        name="contract-suite-toy-agent",
        capabilities=pb.AgentCapabilities(
            streaming=True,
            push_notifications=False,
            extended_agent_card=True,
        ),
    )


async def _wait_for_state(
    handler: DefaultRequestHandlerV2,
    task_id: str,
    owner: str,
    states: set[int],
    *,
    timeout_s: float,
    poll_s: float = 0.05,
) -> pb.Task:
    """Polls `GetTask` until `task.status.state` is in `states`."""
    deadline = time.monotonic() + timeout_s
    last_task: pb.Task | None = None
    while time.monotonic() < deadline:
        last_task = await handler.on_get_task(pb.GetTaskRequest(id=task_id), _ctx(owner))
        if last_task is not None and last_task.status.state in states:
            return last_task
        await asyncio.sleep(poll_s)
    raise AssertionError(
        f"{_CONTRACT_MSG}: task {task_id} did not reach {states} within {timeout_s}s "
        f"(last state={last_task.status.state if last_task else 'MISSING'})"
    )


async def _wait_for_producer_stopped(
    progress: dict[str, float],
    *,
    timeout_s: float = 2.0,
    since: float | None = None,
) -> float:
    """Waits for the toy executor's producer to actually stop (AD-6 signal).

    This *is* the "stops within 2s" assertion (AC-34): it polls
    `progress["cancelled_at"]` (set from inside `_CountingToyExecutor`'s
    `except asyncio.CancelledError` handler) rather than `GetTask`'s status,
    because `_cancel_remote` writes `CANCELED` to the task row synchronously
    from the *cancelling* call -- before the owning worker's producer has
    had any chance to notice -- so `GetTask` cannot tell "the write landed"
    apart from "the producer stopped". Sampling any counter the caller owns
    before this returns would race the in-flight chunk/save AD-6 allows
    (the delay is "until the next save"), which is what made the first cut
    of this suite's remote-cancel tests flaky.

    If `since` is given (e.g. the `time.monotonic()` reading taken right
    before `on_cancel_task` was called), also asserts the producer's own
    stop time is less than `timeout_s` *after* `since` -- the literal AC-34
    "stops within 2s [of cancellation]" bound, not just "within 2s of this
    function being called".

    Returns the producer's stop time (`time.monotonic()` reading).
    """
    deadline = time.monotonic() + timeout_s
    while "cancelled_at" not in progress and time.monotonic() < deadline:
        await asyncio.sleep(0.02)
    assert "cancelled_at" in progress, (
        f"{_CONTRACT_MSG}: the producer did not stop within {timeout_s}s of cancellation "
        f"(progress={progress})"
    )
    stop_time = progress["cancelled_at"]
    if since is not None:
        assert stop_time - since < timeout_s, (
            f"{_CONTRACT_MSG}: the producer stopped {stop_time - since:.3f}s after cancellation, "
            f"expected < {timeout_s}s (AC-34)"
        )
    return stop_time


async def _task_has_completed_event(engine, task_id: str) -> bool:
    """True if any `a2a_task_events` row for `task_id` carries a COMPLETED status.

    Used by the cancel tests to prove the cancellation is durable at the
    event-log level too, not just in the final `a2a_tasks` row: a COMPLETED
    event landing *after* a cancel would mean the producer's work outraced
    the cancellation at the persistence layer, not just in-memory.
    """
    models = get_sdk_models()
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                sa.select(models.event.event_data).where(models.event.task_id == task_id)
            )
        ).scalars().all()
    for data in rows:
        response = pb.StreamResponse()
        response.ParseFromString(data)
        which = response.WhichOneof("payload")
        if which == "status_update" and response.status_update.status.state == pb.TaskState.TASK_STATE_COMPLETED:
            return True
        if which == "task" and response.task.status.state == pb.TaskState.TASK_STATE_COMPLETED:
            return True
    return False


def _pending_tasks() -> set[asyncio.Task]:
    """A snapshot of non-done asyncio tasks, excluding the caller's own task."""
    current = asyncio.current_task()
    return {t for t in asyncio.all_tasks() if not t.done() and t is not current}


async def _assert_no_leaked_tasks(before: set[asyncio.Task]) -> None:
    """Asserts no asyncio task survives beyond `before`'s snapshot.

    `gc.collect()` + a zero-length `asyncio.sleep(0)` give cancelled tasks a
    chance to actually finish unwinding (their `finally` blocks run on the
    next loop iteration, not synchronously at `.cancel()` time) before the
    "after" snapshot is taken.
    """
    gc.collect()
    await asyncio.sleep(0)
    after = _pending_tasks()
    leaked = after - before
    assert not leaked, f"{_CONTRACT_MSG}: pending asyncio tasks leaked: {leaked}"


@pytest.fixture
async def test_async_engine():
    """An `AsyncEngine` on the test DB (port 5433), shared with `db.database`.

    Reuses the shared pool per NFR-4 rather than opening a second engine: by
    the time this fixture runs, `db.database.async_engine` is already bound
    to the test DB because `pytest.ini`'s `env=` block sets
    `SQLALCHEMY_DATABASE_URI` before collection, i.e. before `db.database` is
    first imported.

    Disposes the engine's connection pool after every test. `pytest-asyncio`
    (function-scoped loop by default) tears down and recreates the event
    loop between test functions; without disposing here, a connection
    acquired under this test's loop could be handed to a later test running
    under a *different* loop, surfacing as "Future attached to a different
    loop" errors. The engine itself is still the same shared object (NFR-4);
    disposing only drops its pooled connections, not the engine.
    """
    from db.database import async_engine

    yield async_engine
    await async_engine.dispose()


@pytest.fixture
async def cleanup_a2a_rows(a2a_sdk_tables, test_async_engine):
    """Deletes any `a2a_*` rows this test created, keyed by a unique owner prefix.

    Yields the owner prefix to use (`f"a2a:contract-test:{uuid4()}:"`); every
    owner string a test constructs must start with it, so teardown can find
    and remove exactly the rows this test created and nothing else. The
    `"a2a:"` prefix itself is required by `storage._fail_closed_owner_resolver`
    (AD-3/AC-32).
    """
    prefix = f"a2a:contract-test:{uuid.uuid4()}:"
    yield prefix

    models = get_sdk_models()
    async with test_async_engine.begin() as conn:
        for model in (models.event, models.version, models.task):
            await conn.execute(sa.delete(model).where(model.owner.like(f"{prefix}%")))


# ---------------------------------------------------------------------------
# Behavioural contract (real test DB; two independent handler instances
# simulate two uvicorn workers sharing one database, AC-33).
# ---------------------------------------------------------------------------


@pytest.fixture
async def two_workers(a2a_sdk_tables, test_async_engine):
    """Builds two independent `DefaultRequestHandlerV2` instances (A, B).

    Each comes from its own `build_bound_storage()` call but shares the test
    DB engine, simulating two uvicorn workers (NFR-3). Both share one
    `DatabaseTaskEventStream` built per handler so `on_subscribe_to_task` can
    tail a remote task (AD-1's `event_stream` wiring).
    """
    store_a, stream_a = build_bound_storage(
        engine=test_async_engine, owner_resolver=_resolve_owner_from_context, poll_interval_s=0.1
    )
    store_b, stream_b = build_bound_storage(
        engine=test_async_engine, owner_resolver=_resolve_owner_from_context, poll_interval_s=0.1
    )

    def _make_handler(store, stream, executor):
        return DefaultRequestHandlerV2(
            agent_executor=executor,
            task_store=store,
            agent_card=_agent_card(),
            event_stream=stream,
        )

    handlers: dict[str, DefaultRequestHandlerV2] = {}

    def factory(executor_a: AgentExecutor, executor_b: AgentExecutor | None = None):
        handlers["a"] = _make_handler(store_a, stream_a, executor_a)
        handlers["b"] = _make_handler(store_b, stream_b, executor_b or executor_a)
        return handlers["a"], handlers["b"]

    yield factory

    for handler in handlers.values():
        await handler.aclose()


class TestBehaviouralContract:
    async def test_a_routing_through_registry_models_only(
        self, two_workers, cleanup_a2a_rows, test_async_engine
    ):
        """(a) After one send, rows land in a2a_* tables; default SDK tables never exist."""
        owner = f"{cleanup_a2a_rows}routing"
        executor = _CountingToyExecutor(num_chunks=1, chunk_delay_s=0.0)
        handler_a, _ = two_workers(executor)

        req = _send_request(return_immediately=False)
        result = await handler_a.on_message_send(req, _ctx(owner))
        assert isinstance(result, pb.Task)
        assert result.status.state == pb.TaskState.TASK_STATE_COMPLETED

        models = get_sdk_models()
        async with test_async_engine.connect() as conn:
            task_count = (
                await conn.execute(
                    sa.select(sa.func.count()).select_from(models.task).where(models.task.owner == owner)
                )
            ).scalar_one()
            version_count = (
                await conn.execute(
                    sa.select(sa.func.count())
                    .select_from(models.version)
                    .where(models.version.owner == owner)
                )
            ).scalar_one()
            event_count = (
                await conn.execute(
                    sa.select(sa.func.count())
                    .select_from(models.event)
                    .where(models.event.owner == owner)
                )
            ).scalar_one()
            assert task_count == 1, _CONTRACT_MSG
            assert version_count == 1, _CONTRACT_MSG
            assert event_count >= 1, _CONTRACT_MSG

        def _sync_has_table(sync_conn, name: str) -> bool:
            return sa.inspect(sync_conn).has_table(name)

        async with test_async_engine.connect() as conn:
            for default_table in ("tasks", "task_events", "task_versions"):
                has_table = await conn.run_sync(_sync_has_table, default_table)
                assert has_table is False, (
                    f"{_CONTRACT_MSG}: default SDK table {default_table!r} unexpectedly exists"
                )

    async def test_b_return_immediately_and_history_length(self, two_workers, cleanup_a2a_rows):
        """(b) return_immediately gives a non-terminal task first; historyLength=1 caps history."""
        owner = f"{cleanup_a2a_rows}return-immediately"
        executor = _CountingToyExecutor(num_chunks=3, chunk_delay_s=0.05)
        handler_a, handler_b = two_workers(executor)

        req = _send_request(return_immediately=True)
        first = await handler_a.on_message_send(req, _ctx(owner))
        assert isinstance(first, pb.Task)
        assert first.status.state not in {
            pb.TaskState.TASK_STATE_COMPLETED,
            pb.TaskState.TASK_STATE_FAILED,
            pb.TaskState.TASK_STATE_CANCELED,
        }, _CONTRACT_MSG

        completed = await _wait_for_state(
            handler_b,
            first.id,
            owner,
            {pb.TaskState.TASK_STATE_COMPLETED},
            timeout_s=5.0,
        )
        assert len(completed.artifacts) >= 1, _CONTRACT_MSG

        limited = await handler_b.on_get_task(
            pb.GetTaskRequest(id=first.id, history_length=1), _ctx(owner)
        )
        assert len(limited.history) <= 1, _CONTRACT_MSG

    async def test_c_subscribe_remote_yields_snapshot_then_terminal(
        self, two_workers, cleanup_a2a_rows
    ):
        """(c) SubscribeToTask on B while A runs yields the snapshot, then events, then stops."""
        owner = f"{cleanup_a2a_rows}subscribe"
        executor = _CountingToyExecutor(num_chunks=3, chunk_delay_s=0.1)
        handler_a, handler_b = two_workers(executor)

        req = _send_request(return_immediately=True)
        first = await handler_a.on_message_send(req, _ctx(owner))

        async def _collect() -> list:
            events = []
            async for event in handler_b.on_subscribe_to_task(
                pb.SubscribeToTaskRequest(id=first.id), _ctx(owner)
            ):
                events.append(event)
            return events

        events = await asyncio.wait_for(_collect(), timeout=5.0)
        assert events, _CONTRACT_MSG
        last = events[-1]
        state = last.status.state if isinstance(last, (pb.Task, pb.TaskStatusUpdateEvent)) else None
        assert state == pb.TaskState.TASK_STATE_COMPLETED, _CONTRACT_MSG

    async def test_d_foreign_owner_is_task_not_found_and_excluded_from_list(
        self, two_workers, cleanup_a2a_rows, test_async_engine
    ):
        """(d) A different owner gets task-not-found; ListTasks excludes the task; K1's row
        is untouched by K2's attempts."""
        owner = f"{cleanup_a2a_rows}owner1"
        other_owner = f"{cleanup_a2a_rows}owner2"
        executor = _CountingToyExecutor(num_chunks=1, chunk_delay_s=0.0)
        handler_a, handler_b = two_workers(executor)

        req = _send_request(return_immediately=False)
        task = await handler_a.on_message_send(req, _ctx(owner))

        with pytest.raises(TaskNotFoundError):
            await handler_b.on_get_task(pb.GetTaskRequest(id=task.id), _ctx(other_owner))
        with pytest.raises(TaskNotFoundError):
            await handler_b.on_cancel_task(pb.CancelTaskRequest(id=task.id), _ctx(other_owner))
        with pytest.raises(TaskNotFoundError):
            async for _ in handler_b.on_subscribe_to_task(
                pb.SubscribeToTaskRequest(id=task.id), _ctx(other_owner)
            ):
                pass

        listed = await handler_b.on_list_tasks(pb.ListTasksRequest(), _ctx(other_owner))
        assert task.id not in {t.id for t in listed.tasks}, _CONTRACT_MSG

    async def test_d2_foreign_owner_send_reusing_k1_task_id(
        self, two_workers, cleanup_a2a_rows, test_async_engine
    ):
        """(d2) K2 sending with K1's taskId gets task-not-found; the executor never runs for
        it; K1's `a2a_tasks` row (owner/status/last_updated) is byte-identical before/after."""
        owner_k1 = f"{cleanup_a2a_rows}k1"
        owner_k2 = f"{cleanup_a2a_rows}k2"
        call_count = {"n": 0}

        class _CountingExecutor(_CountingToyExecutor):
            async def execute(self, context, event_queue):
                call_count["n"] += 1
                await super().execute(context, event_queue)

        handler_a, handler_b = two_workers(_CountingExecutor(num_chunks=0))

        k1_task = await handler_a.on_message_send(
            _send_request(return_immediately=False), _ctx(owner_k1)
        )
        assert k1_task.status.state == pb.TaskState.TASK_STATE_COMPLETED
        calls_after_k1 = call_count["n"]

        models = get_sdk_models()
        async with test_async_engine.connect() as conn:
            before_row = (
                await conn.execute(
                    sa.select(models.task.owner, models.task.status, models.task.last_updated).where(
                        models.task.id == k1_task.id
                    )
                )
            ).one()

        k2_attempt = pb.SendMessageRequest(
            message=pb.Message(
                message_id=str(uuid.uuid4()),
                role=pb.ROLE_USER,
                parts=[pb.Part(text="steal")],
                task_id=k1_task.id,
            ),
        )
        with pytest.raises(TaskNotFoundError):
            await handler_b.on_message_send(k2_attempt, _ctx(owner_k2))

        assert call_count["n"] == calls_after_k1, (
            f"{_CONTRACT_MSG}: the executor ran for a foreign owner's send naming K1's taskId"
        )

        async with test_async_engine.connect() as conn:
            after_row = (
                await conn.execute(
                    sa.select(models.task.owner, models.task.status, models.task.last_updated).where(
                        models.task.id == k1_task.id
                    )
                )
            ).one()
        assert tuple(before_row) == tuple(after_row), (
            f"{_CONTRACT_MSG}: K1's a2a_tasks row changed after K2's rejected send on its taskId "
            f"({tuple(before_row)} -> {tuple(after_row)})"
        )

    async def test_d3_foreign_owner_cancel_and_subscribe_on_non_terminal_task(
        self, two_workers, cleanup_a2a_rows
    ):
        """(d3) A foreign owner's Cancel/Subscribe against a *non-terminal* task is still
        task-not-found (not merely a side effect of the task already being terminal, as in
        (d))."""
        owner = f"{cleanup_a2a_rows}owner1-nonterminal"
        other_owner = f"{cleanup_a2a_rows}owner2-nonterminal"
        executor = _CountingToyExecutor(num_chunks=20, chunk_delay_s=0.1)
        handler_a, handler_b = two_workers(executor)

        task = await handler_a.on_message_send(
            _send_request(return_immediately=True), _ctx(owner)
        )
        await _wait_for_state(
            handler_a, task.id, owner, {pb.TaskState.TASK_STATE_WORKING}, timeout_s=2.0
        )

        with pytest.raises(TaskNotFoundError):
            await handler_b.on_cancel_task(pb.CancelTaskRequest(id=task.id), _ctx(other_owner))
        with pytest.raises(TaskNotFoundError):
            async for _ in handler_b.on_subscribe_to_task(
                pb.SubscribeToTaskRequest(id=task.id), _ctx(other_owner)
            ):
                pass

        # The task must still be running, untouched by the foreign owner's attempts --
        # a real owner cancel still works afterward.
        still_running = await handler_a.on_get_task(pb.GetTaskRequest(id=task.id), _ctx(owner))
        assert still_running.status.state == pb.TaskState.TASK_STATE_WORKING, _CONTRACT_MSG
        cancelled = await handler_a.on_cancel_task(pb.CancelTaskRequest(id=task.id), _ctx(owner))
        assert cancelled.status.state == pb.TaskState.TASK_STATE_CANCELED, _CONTRACT_MSG

    async def test_e_remote_cancel_stops_execution_within_2s(
        self, two_workers, cleanup_a2a_rows, test_async_engine
    ):
        """(e) Remote CancelTask on B stops A's execution within 2s; final state is CANCELED;
        no COMPLETED event ever lands for the task."""
        owner = f"{cleanup_a2a_rows}remote-cancel"
        counter = {"n": 0}
        executor = _CountingToyExecutor(counter=counter, num_chunks=100, chunk_delay_s=0.03)
        handler_a, handler_b = two_workers(executor)

        req = _send_request(return_immediately=True)
        task = await handler_a.on_message_send(req, _ctx(owner))

        await _wait_for_state(
            handler_b,
            task.id,
            owner,
            {pb.TaskState.TASK_STATE_WORKING, pb.TaskState.TASK_STATE_SUBMITTED},
            timeout_s=2.0,
        )

        t_cancel = time.monotonic()
        cancelled = await handler_b.on_cancel_task(pb.CancelTaskRequest(id=task.id), _ctx(owner))
        assert cancelled.status.state == pb.TaskState.TASK_STATE_CANCELED, _CONTRACT_MSG

        # Primary assertion -- this *is* AC-34's "stops within 2s": the
        # producer's own CancelledError, timed from `t_cancel`, not a fixed
        # sleep (AD-6: the delay is "until the next save").
        await _wait_for_producer_stopped(counter, timeout_s=2.0, since=t_cancel)

        # Secondary / defensive check only: the chunk counter should also be
        # stable a moment later. Not the primary signal (see helper above).
        sample_1 = counter["n"]
        await asyncio.sleep(0.2)
        sample_2 = counter["n"]
        assert sample_2 == sample_1, (
            f"{_CONTRACT_MSG}: counter kept increasing after the producer reported itself "
            f"cancelled ({sample_1} -> {sample_2})"
        )

        final = await handler_b.on_get_task(pb.GetTaskRequest(id=task.id), _ctx(owner))
        assert final.status.state == pb.TaskState.TASK_STATE_CANCELED, _CONTRACT_MSG

        assert not await _task_has_completed_event(test_async_engine, task.id), (
            f"{_CONTRACT_MSG}: a COMPLETED event landed in a2a_task_events for a remotely "
            "cancelled task"
        )

    async def test_f_local_cancel_stops_execution_within_2s(
        self, two_workers, cleanup_a2a_rows, test_async_engine
    ):
        """(f) Local CancelTask on A (the executing worker) gives the same guarantees as (e)."""
        owner = f"{cleanup_a2a_rows}local-cancel"
        counter = {"n": 0}
        executor = _CountingToyExecutor(counter=counter, num_chunks=100, chunk_delay_s=0.03)
        handler_a, _ = two_workers(executor)

        req = _send_request(return_immediately=True)
        task = await handler_a.on_message_send(req, _ctx(owner))

        await _wait_for_state(
            handler_a,
            task.id,
            owner,
            {pb.TaskState.TASK_STATE_WORKING, pb.TaskState.TASK_STATE_SUBMITTED},
            timeout_s=2.0,
        )

        t_cancel = time.monotonic()
        cancelled = await handler_a.on_cancel_task(pb.CancelTaskRequest(id=task.id), _ctx(owner))
        assert cancelled.status.state == pb.TaskState.TASK_STATE_CANCELED, _CONTRACT_MSG

        await _wait_for_producer_stopped(counter, timeout_s=2.0, since=t_cancel)

        sample_1 = counter["n"]
        await asyncio.sleep(0.2)
        sample_2 = counter["n"]
        assert sample_2 == sample_1, (
            f"{_CONTRACT_MSG}: counter kept increasing after the producer reported itself "
            f"cancelled ({sample_1} -> {sample_2})"
        )

        final = await handler_a.on_get_task(pb.GetTaskRequest(id=task.id), _ctx(owner))
        assert final.status.state == pb.TaskState.TASK_STATE_CANCELED, _CONTRACT_MSG

        assert not await _task_has_completed_event(test_async_engine, task.id), (
            f"{_CONTRACT_MSG}: a COMPLETED event landed in a2a_task_events for a locally "
            "cancelled task"
        )

    async def test_g_remote_cancel_during_silence_needs_keepalives(
        self, two_workers, cleanup_a2a_rows
    ):
        """(g) Remote cancel during silence stops the producer within 2s only with
        keepalives (AD-6).

        `GetTask` cannot be the signal here: `_cancel_remote` writes `CANCELED`
        to the task row synchronously from the *cancelling* call, before the
        owning worker's producer ever notices -- so `GetTask` would read
        `CANCELED` immediately in both the with- and without-keepalive cases.
        Only the producer's own `progress["cancelled_at"]` (set from inside its
        `except asyncio.CancelledError` handler, see `_CountingToyExecutor`)
        can distinguish "the write landed" from "the producer actually
        stopped".
        """
        owner_with = f"{cleanup_a2a_rows}silent-with-keepalive"
        progress_with: dict[str, float] = {"n": 0}
        executor_with = _CountingToyExecutor(
            counter=progress_with, silent_duration_s=5.0, keepalive_interval_s=0.5
        )
        handler_a, handler_b = two_workers(executor_with)

        task = await handler_a.on_message_send(_send_request(return_immediately=True), _ctx(owner_with))
        await _wait_for_state(
            handler_b, task.id, owner_with, {pb.TaskState.TASK_STATE_WORKING}, timeout_s=2.0
        )
        t_cancel = time.monotonic()
        await handler_b.on_cancel_task(pb.CancelTaskRequest(id=task.id), _ctx(owner_with))

        await _wait_for_producer_stopped(progress_with, timeout_s=2.0, since=t_cancel)

        before_close = _pending_tasks()
        await handler_a.aclose()
        await handler_b.aclose()
        await _assert_no_leaked_tasks(before_close)

        owner_without = f"{cleanup_a2a_rows}silent-no-keepalive"
        progress_without: dict[str, float] = {"n": 0}
        executor_without = _CountingToyExecutor(
            counter=progress_without, silent_duration_s=5.0, keepalive_interval_s=None
        )
        handler_a2, handler_b2 = two_workers(executor_without)

        task2 = await handler_a2.on_message_send(
            _send_request(return_immediately=True), _ctx(owner_without)
        )
        await _wait_for_state(
            handler_b2, task2.id, owner_without, {pb.TaskState.TASK_STATE_WORKING}, timeout_s=2.0
        )
        await handler_b2.on_cancel_task(pb.CancelTaskRequest(id=task2.id), _ctx(owner_without))

        await asyncio.sleep(2.0)
        assert "cancelled_at" not in progress_without and "completed_at" not in progress_without, (
            "AD-6 contradicted: without keepalives, the producer was interrupted (or ran to "
            f"completion) within 2s of a remote cancel during silence (progress={progress_without}). "
            "This documents a design assumption -- if this now fails, step_016's "
            "coalesce/keepalive bridge logic may need to change."
        )

        # Cleanup: the task's DB status is already terminal (CANCELED), written
        # synchronously by the remote cancel above, so a further on_cancel_task
        # call -- local or remote -- is itself rejected with
        # TaskNotCancelableError before it can touch the producer (same guard
        # as scenario (h)). The producer is still genuinely running (that is
        # the point of this scenario), so the only bounded way to let it
        # reach a terminal state is to wait out the rest of its silent
        # duration; this keeps the whole test under ~15s.
        with pytest.raises(TaskNotCancelableError):
            await handler_a2.on_cancel_task(pb.CancelTaskRequest(id=task2.id), _ctx(owner_without))
        deadline = time.monotonic() + 5.0
        while (
            "cancelled_at" not in progress_without
            and "completed_at" not in progress_without
            and time.monotonic() < deadline
        ):
            await asyncio.sleep(0.05)
        assert "cancelled_at" in progress_without or "completed_at" in progress_without, (
            f"cleanup failed to let the test's own background producer finish (progress={progress_without})"
        )

    async def test_h_cancel_completed_task_is_not_cancelable(self, two_workers, cleanup_a2a_rows):
        """(h) Cancel on a completed task raises task-not-cancelable."""
        owner = f"{cleanup_a2a_rows}completed"
        executor = _CountingToyExecutor(num_chunks=1, chunk_delay_s=0.0)
        handler_a, handler_b = two_workers(executor)

        task = await handler_a.on_message_send(_send_request(return_immediately=False), _ctx(owner))
        assert task.status.state == pb.TaskState.TASK_STATE_COMPLETED

        with pytest.raises(TaskNotCancelableError):
            await handler_b.on_cancel_task(pb.CancelTaskRequest(id=task.id), _ctx(owner))

    async def test_i_task_id_and_context_id_mismatches(self, two_workers, cleanup_a2a_rows):
        """(i) A completed taskId is not re-executed; a mismatched contextId is rejected."""
        owner = f"{cleanup_a2a_rows}mismatch"
        call_count = {"n": 0}

        class _CountingExecutor(_CountingToyExecutor):
            async def execute(self, context, event_queue):
                call_count["n"] += 1
                await super().execute(context, event_queue)

        handler_a, handler_b = two_workers(_CountingExecutor(num_chunks=0))

        completed = await handler_a.on_message_send(
            _send_request(return_immediately=False), _ctx(owner)
        )
        assert completed.status.state == pb.TaskState.TASK_STATE_COMPLETED
        calls_after_first = call_count["n"]

        follow_up = pb.SendMessageRequest(
            message=pb.Message(
                message_id=str(uuid.uuid4()),
                role=pb.ROLE_USER,
                parts=[pb.Part(text="again")],
                task_id=completed.id,
            ),
        )
        with pytest.raises(UnsupportedOperationError):
            await handler_b.on_message_send(follow_up, _ctx(owner))
        assert call_count["n"] == calls_after_first, (
            f"{_CONTRACT_MSG}: executor ran for a message naming a terminal task"
        )

        mismatched = pb.SendMessageRequest(
            message=pb.Message(
                message_id=str(uuid.uuid4()),
                role=pb.ROLE_USER,
                parts=[pb.Part(text="again")],
                task_id=completed.id,
                context_id=str(uuid.uuid4()),
            ),
        )
        with pytest.raises(InvalidParamsError):
            await handler_b.on_message_send(mismatched, _ctx(owner))

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "a2a-sdk 1.2.2: ActiveTask.__init__ spawns two EventQueueSource dispatcher tasks "
            "before ActiveTask.start() runs; when start() rejects a terminal-task send with "
            "UnsupportedOperationError, ActiveTaskRegistry._on_active_task_cleanup only drops "
            "the registry entry -- it never calls ActiveTask.aclose() -- so both dispatcher "
            "tasks are never cancelled and leak until event-loop shutdown. Documented here per "
            "review-round item 9 rather than worked around; re-check on every a2a-sdk pin bump."
        ),
    )
    async def test_i2_rejected_send_on_terminal_task_leaks_two_tasks(
        self, two_workers, cleanup_a2a_rows
    ):
        """(i2) xfail-documents a known SDK leak: 2 pending EventQueueSource dispatcher tasks
        per rejected send that names an already-terminal task."""
        owner = f"{cleanup_a2a_rows}rejected-send-leak"
        handler_a, handler_b = two_workers(_CountingToyExecutor(num_chunks=0))

        completed = await handler_a.on_message_send(
            _send_request(return_immediately=False), _ctx(owner)
        )
        assert completed.status.state == pb.TaskState.TASK_STATE_COMPLETED

        before = _pending_tasks()
        follow_up = pb.SendMessageRequest(
            message=pb.Message(
                message_id=str(uuid.uuid4()),
                role=pb.ROLE_USER,
                parts=[pb.Part(text="again")],
                task_id=completed.id,
            ),
        )
        with pytest.raises(UnsupportedOperationError):
            await handler_b.on_message_send(follow_up, _ctx(owner))

        await _assert_no_leaked_tasks(before)

    async def test_j_list_tasks_status_filter_on_pg_json(self, two_workers, cleanup_a2a_rows):
        """(j) The ListTasks status filter works against the PG JSON `status` column."""
        owner = f"{cleanup_a2a_rows}list-filter"
        handler_a, handler_b = two_workers(_CountingToyExecutor(num_chunks=0))

        completed = await handler_a.on_message_send(
            _send_request(return_immediately=False), _ctx(owner)
        )
        assert completed.status.state == pb.TaskState.TASK_STATE_COMPLETED

        completed_only = await handler_b.on_list_tasks(
            pb.ListTasksRequest(status=pb.TaskState.TASK_STATE_COMPLETED), _ctx(owner)
        )
        assert completed.id in {t.id for t in completed_only.tasks}, _CONTRACT_MSG

        failed_only = await handler_b.on_list_tasks(
            pb.ListTasksRequest(status=pb.TaskState.TASK_STATE_FAILED), _ctx(owner)
        )
        assert completed.id not in {t.id for t in failed_only.tasks}, _CONTRACT_MSG

    async def test_k_aclose_leaves_no_pending_tasks(self, two_workers, cleanup_a2a_rows):
        """(k) `handler.aclose()` drains the active-task registry; no asyncio tasks leak."""
        owner = f"{cleanup_a2a_rows}aclose"
        handler_a, handler_b = two_workers(_CountingToyExecutor(num_chunks=1, chunk_delay_s=0.0))

        await handler_a.on_message_send(_send_request(return_immediately=False), _ctx(owner))

        before = _pending_tasks()
        await handler_a.aclose()
        await handler_b.aclose()
        await _assert_no_leaked_tasks(before)
