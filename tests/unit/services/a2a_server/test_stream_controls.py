"""Unit coverage for `services.a2a_server.stream_controls` (step_017 fix round 1).

CRITICAL-1: the bulkhead must actually admit a stream when capacity is free,
and must release every acquired slot exactly once, on every exit path
(success, early reject, exception, client disconnect). RB-2: the wall-clock
cap and the liveness check must end a stream that outlives its budget or
whose task has gone missing/terminal, without truncating in-flight events.

No DB, no HTTP: everything here is driven with fakes, per this module's own
docstring ("Extracted ... for unit testability without an HTTP round trip").
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, List

import pytest

from a2a.types.a2a_pb2 import TaskState
from services.a2a_server.identity import A2ARequestLog
from services.a2a_server.stream_controls import (
    bounded_sse_iterator,
    reset_for_tests,
    try_acquire_stream_bulkhead,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_bulkhead_state():
    reset_for_tests()
    yield
    reset_for_tests()


def _cfg(*, app_cap: int = 10, key_cap: int = 10, worker_cap: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        max_concurrent_streams_per_app=app_cap,
        max_concurrent_streams_per_key=key_cap,
        max_concurrent_streams_worker=worker_cap,
    )


class TestBulkheadAdmission:
    async def test_admits_a_stream_when_capacity_is_free(self):
        """CRITICAL-1: a real `asyncio.wait_for(sem.acquire(), timeout=0)`
        never acquires even an idle semaphore -- this is the regression this
        test guards against."""
        bulkhead = await try_acquire_stream_bulkhead(_cfg(), app_id=1, key_id=1)
        assert bulkhead is not None
        bulkhead.release()

    async def test_worker_cap_rejects_the_nplus1th_stream(self):
        cfg = _cfg(worker_cap=1)
        first = await try_acquire_stream_bulkhead(cfg, app_id=1, key_id=1)
        assert first is not None

        second = await try_acquire_stream_bulkhead(cfg, app_id=2, key_id=2)
        assert second is None

        first.release()
        third = await try_acquire_stream_bulkhead(cfg, app_id=3, key_id=3)
        assert third is not None
        third.release()

    async def test_per_app_cap_rejects_a_second_stream_for_the_same_app(self):
        cfg = _cfg(app_cap=1, key_cap=10, worker_cap=10)
        first = await try_acquire_stream_bulkhead(cfg, app_id=1, key_id=1)
        assert first is not None

        second = await try_acquire_stream_bulkhead(cfg, app_id=1, key_id=2)
        assert second is None

        first.release()

    async def test_per_key_cap_rejects_a_second_stream_for_the_same_key(self):
        cfg = _cfg(app_cap=10, key_cap=1, worker_cap=10)
        first = await try_acquire_stream_bulkhead(cfg, app_id=1, key_id=7)
        assert first is not None

        second = await try_acquire_stream_bulkhead(cfg, app_id=2, key_id=7)
        assert second is None

        first.release()

    async def test_a_rejected_app_slot_does_not_leak_into_the_key_counter(self):
        """When the per-key cap rejects, the per-app slot it already reserved
        must be released too (no partial acquisition left behind)."""
        from services.a2a_server import stream_controls as sc

        cfg = _cfg(app_cap=10, key_cap=1, worker_cap=10)
        held = await try_acquire_stream_bulkhead(cfg, app_id=1, key_id=1)
        assert held is not None

        rejected = await try_acquire_stream_bulkhead(cfg, app_id=1, key_id=1)
        assert rejected is None
        # Only the one held stream's app-slot should remain reserved.
        assert sc._app_stream_counts.get(1) == 1

        held.release()
        assert 1 not in sc._app_stream_counts

    async def test_counters_return_to_zero_after_release(self):
        from services.a2a_server import stream_controls as sc

        cfg = _cfg()
        bulkhead = await try_acquire_stream_bulkhead(cfg, app_id=9, key_id=9)
        assert bulkhead is not None
        assert sc._app_stream_counts.get(9) == 1
        assert sc._key_stream_counts.get(9) == 1

        bulkhead.release()
        assert 9 not in sc._app_stream_counts
        assert 9 not in sc._key_stream_counts
        assert not sc._get_worker_stream_semaphore(cfg.max_concurrent_streams_worker).locked()

    async def test_release_is_idempotent(self):
        bulkhead = await try_acquire_stream_bulkhead(_cfg(), app_id=1, key_id=1)
        assert bulkhead is not None
        bulkhead.release()
        bulkhead.release()  # must not raise (ValueError from over-releasing a BoundedSemaphore)


class _FakeStored:
    def __init__(self, state: int) -> None:
        self.task = SimpleNamespace(status=SimpleNamespace(state=state))
        self.version = 1


class _FakeStore:
    """A fake `rt.store` whose `.get()` result is swappable mid-test."""

    def __init__(self) -> None:
        self.result: Any = None
        self.calls = 0
        self.raise_timeout = False

    async def get(self, task_id: str, ctx: Any) -> Any:
        self.calls += 1
        if self.raise_timeout:
            await asyncio.sleep(10)  # never resolves within the test's timeout
        return self.result


async def _forever_pending() -> AsyncIterator[Dict[str, Any]]:
    """An inner iterator that never yields and never completes."""
    await asyncio.Event().wait()
    yield {}  # pragma: no cover - unreachable


async def _collect(gen: AsyncIterator[Dict[str, Any]], *, limit: int = 100) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    async for item in gen:
        out.append(item)
        if len(out) >= limit:
            break
    return out


class TestBoundedSseIteratorWallClockAndLiveness:
    async def test_wall_clock_cap_ends_the_stream_and_releases_the_bulkhead(self):
        released = {"count": 0}

        class _Bulkhead:
            def release(self) -> None:
                released["count"] += 1

        rt = SimpleNamespace(store=_FakeStore())
        request_log = A2ARequestLog(method="SendStreamingMessage")

        items = await _collect(
            bounded_sse_iterator(
                _forever_pending(),
                rt=rt,
                owner="a2a:1:1:" + "0" * 64,
                task_id="t1",
                stream_max_seconds=0.05,
                liveness_interval_seconds=10,
                event_poll_seconds=0.1,
                bulkhead=_Bulkhead(),
                request_log=request_log,
                emit_log=lambda: None,
            )
        )
        assert items == []
        assert released["count"] == 1
        assert request_log.outcome == "stream_wall_clock_cap"

    async def test_missing_task_drains_then_ends_the_stream(self):
        store = _FakeStore()
        store.result = None  # task missing

        async def _one_then_hang() -> AsyncIterator[Dict[str, Any]]:
            yield {"event": "message", "data": '{"result": {}}'}
            await asyncio.Event().wait()
            yield {}  # pragma: no cover

        rt = SimpleNamespace(store=store)
        request_log = A2ARequestLog(method="SubscribeToTask")

        items = await _collect(
            bounded_sse_iterator(
                _one_then_hang(),
                rt=rt,
                owner="a2a:1:1:" + "0" * 64,
                task_id="t1",
                stream_max_seconds=30,
                liveness_interval_seconds=0.02,
                event_poll_seconds=0.01,
                bulkhead=None,
                request_log=request_log,
                emit_log=lambda: None,
            )
        )
        assert len(items) == 1
        assert request_log.outcome == "stream_task_missing"

    async def test_terminal_task_drains_then_ends_the_stream(self):
        store = _FakeStore()
        store.result = _FakeStored(TaskState.TASK_STATE_COMPLETED)

        rt = SimpleNamespace(store=store)
        request_log = A2ARequestLog(method="SubscribeToTask")

        items = await _collect(
            bounded_sse_iterator(
                _forever_pending(),
                rt=rt,
                owner="a2a:1:1:" + "0" * 64,
                task_id="t1",
                stream_max_seconds=30,
                liveness_interval_seconds=0.02,
                event_poll_seconds=0.01,
                bulkhead=None,
                request_log=request_log,
                emit_log=lambda: None,
            )
        )
        assert items == []
        assert request_log.outcome == "stream_task_terminal"

    async def test_client_disconnect_releases_the_bulkhead_exactly_once(self):
        released = {"count": 0}

        class _Bulkhead:
            def release(self) -> None:
                released["count"] += 1

        rt = SimpleNamespace(store=_FakeStore())
        request_log = A2ARequestLog(method="SendStreamingMessage")

        gen = bounded_sse_iterator(
            _forever_pending(),
            rt=rt,
            owner="a2a:1:1:" + "0" * 64,
            task_id="t1",
            stream_max_seconds=30,
            liveness_interval_seconds=10,
            event_poll_seconds=0.1,
            bulkhead=_Bulkhead(),
            request_log=request_log,
                emit_log=lambda: None,
        )
        started = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0.02)
        started.cancel()
        with pytest.raises(asyncio.CancelledError):
            await started
        await gen.aclose()

        assert released["count"] == 1
        assert request_log.outcome in {"client_disconnect", "stream_ended"}

    async def test_emit_log_is_called_from_finally_after_the_bulkhead_release(self):
        """LOW-2 (step_017 reliability-auditor, step_018): the request-log
        emission must happen from `bounded_sse_iterator`'s own `finally`,
        never rely on `resp.background` alone."""
        calls: List[str] = []

        class _Bulkhead:
            def release(self) -> None:
                calls.append("bulkhead_released")

        rt = SimpleNamespace(store=_FakeStore())
        request_log = A2ARequestLog(method="SendStreamingMessage")

        await _collect(
            bounded_sse_iterator(
                _forever_pending(),
                rt=rt,
                owner="a2a:1:1:" + "0" * 64,
                task_id="t1",
                stream_max_seconds=0.05,
                liveness_interval_seconds=10,
                event_poll_seconds=0.1,
                bulkhead=_Bulkhead(),
                request_log=request_log,
                emit_log=lambda: calls.append("log_emitted"),
            )
        )
        assert calls == ["bulkhead_released", "log_emitted"]

    async def test_a_raising_emit_log_never_breaks_teardown(self):
        rt = SimpleNamespace(store=_FakeStore())
        request_log = A2ARequestLog(method="SendStreamingMessage")

        def _boom() -> None:
            raise RuntimeError("emit_log blew up")

        items = await _collect(
            bounded_sse_iterator(
                _forever_pending(),
                rt=rt,
                owner="a2a:1:1:" + "0" * 64,
                task_id="t1",
                stream_max_seconds=0.05,
                liveness_interval_seconds=10,
                event_poll_seconds=0.1,
                bulkhead=None,
                request_log=request_log,
                emit_log=_boom,
            )
        )
        assert items == []
        assert request_log.outcome == "stream_wall_clock_cap"

    async def test_an_unexpected_inner_exception_still_releases_the_bulkhead_once(self):
        released = {"count": 0}

        class _Bulkhead:
            def release(self) -> None:
                released["count"] += 1

        class _Boom(RuntimeError):
            pass

        async def _raises() -> AsyncIterator[Dict[str, Any]]:
            yield {"event": "message", "data": '{"result": {}}'}
            raise _Boom("inner failure")

        rt = SimpleNamespace(store=_FakeStore())
        request_log = A2ARequestLog(method="SendStreamingMessage")

        gen = bounded_sse_iterator(
            _raises(),
            rt=rt,
            owner="a2a:1:1:" + "0" * 64,
            task_id="t1",
            stream_max_seconds=30,
            liveness_interval_seconds=10,
            event_poll_seconds=0.1,
            bulkhead=_Bulkhead(),
            request_log=request_log,
                emit_log=lambda: None,
        )
        got = await gen.__anext__()
        assert got["event"] == "message"
        with pytest.raises(_Boom):
            await gen.__anext__()

        assert released["count"] == 1
