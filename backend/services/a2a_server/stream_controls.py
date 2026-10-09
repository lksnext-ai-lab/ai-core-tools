"""RB-2/RB-3: SSE stream bulkhead and wall-clock/liveness guard (step_017 fix round 1).

Extracted out of `routers/a2a_server/router.py` for unit testability without
an HTTP round trip (fix round 1, HIGH-4).

- `StreamBulkhead`/`try_acquire_stream_bulkhead`: a per-app, per-API-key and
  per-worker cap on concurrent SSE streams (RB-3).
- `bounded_sse_iterator`: wraps the SDK's own SSE body iterator with a hard
  wall-clock cap and a periodic `store.get` liveness check (RB-2), and
  applies `response_sanitizer.sanitize_sse_item` to every event (RB-4).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any, AsyncGenerator, Callable, Dict, Optional

import anyio

from services.a2a_server.identity import A2ARequestLog, context_for_owner
from services.a2a_server.response_sanitizer import extract_task_id_from_sse_item, sanitize_sse_item
from services.a2a_server.task_states import TERMINAL_TASK_STATES
from utils.logger import get_logger

logger = get_logger(__name__)

# Bounds the cancel-safe teardown phase in `bounded_sse_iterator`'s `finally`
# (fix round 1, MEDIUM-9): a hung downstream `aclose()` must never block this
# worker's event loop forever on a client disconnect.
_TEARDOWN_BUDGET_SECONDS = 5.0


# ---------------------------------------------------------------------------
# RB-3: bulkhead
# ---------------------------------------------------------------------------

#: Per-worker bulkhead semaphore. Built once, lazily, at fixed size (fix
#: round 1, CRITICAL-1: never resized while permits may be held -- a resize
#: would require either shrinking a semaphore mid-flight, which asyncio does
#: not support safely, or silently abandoning the old one's accounting).
#: `reset_for_tests` is the *only* supported way to replace it.
_worker_stream_semaphore: Optional[asyncio.Semaphore] = None

# RB-3: per-app / per-key concurrent-stream counters. Plain dicts: every
# mutation here happens without an intervening `await`, so there is no race
# window within a single worker's event loop (mirrors the in-memory counters
# in `services/rate_limit_service.py`). Per-worker, like every other
# in-memory limiter in this codebase (see `routers/controls/ip_rate_limit.py`'s
# docstring).
_app_stream_counts: Dict[int, int] = {}
_key_stream_counts: Dict[int, int] = {}


def reset_for_tests() -> None:
    """Clears every bulkhead counter and rebuilds the worker semaphore.

    Tests that change `A2A_MAX_CONCURRENT_STREAMS_WORKER` (via
    `get_a2a_config.cache_clear()`) must call this too -- the semaphore is
    deliberately never resized in place (CRITICAL-1).
    """
    global _worker_stream_semaphore
    _worker_stream_semaphore = None
    _app_stream_counts.clear()
    _key_stream_counts.clear()


def _get_worker_stream_semaphore(size: int) -> asyncio.Semaphore:
    global _worker_stream_semaphore
    if _worker_stream_semaphore is None:
        _worker_stream_semaphore = asyncio.BoundedSemaphore(size)
    return _worker_stream_semaphore


async def _acquire_worker_slot(semaphore: asyncio.Semaphore) -> bool:
    """Non-blocking acquire (fix round 1, CRITICAL-1).

    `asyncio.wait_for(sem.acquire(), timeout=0)` does **not** reliably
    acquire an available permit: `wait_for` schedules `acquire()` as a task
    and races it against an already-expired timeout, and with `timeout=0`
    the cancellation can win the race even though the semaphore had permits
    free (verified: an idle `asyncio.Semaphore(5)` was reported "NOT
    acquired, value 5" under that pattern). `Semaphore.locked()` plus an
    unconditional `acquire()` has no such race: `locked()` is a plain
    synchronous check (no `await`), and the `acquire()` call that follows it
    in the same synchronous slice of this coroutine sees the same `_value`
    `locked()` just read -- nothing else can run on this single-threaded
    event loop between the two statements, since `acquire()` itself never
    actually suspends when a permit is already free (its internal `while
    self._value <= 0` loop body never runs, so no real yield point is hit).
    """
    if semaphore.locked():
        return False
    await semaphore.acquire()
    return True


def _try_reserve_slot(counts: Dict[int, int], key: int, cap: int) -> bool:
    if cap <= 0:
        return True
    current = counts.get(key, 0)
    if current >= cap:
        return False
    counts[key] = current + 1
    return True


def _release_slot(counts: Dict[int, int], key: int) -> None:
    current = counts.get(key, 0)
    if current <= 1:
        counts.pop(key, None)
    else:
        counts[key] = current - 1


class StreamBulkhead:
    """Holds the acquired worker/app/key stream slots for one request,
    released exactly once (`release`), whether the request fails before
    streaming even starts or only after the SSE response finishes."""

    def __init__(self, *, worker_acquired: bool, app_id: int, key_id: int) -> None:
        self._worker_acquired = worker_acquired
        self._app_id = app_id
        self._key_id = key_id
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        if self._worker_acquired and _worker_stream_semaphore is not None:
            _worker_stream_semaphore.release()
        _release_slot(_app_stream_counts, self._app_id)
        _release_slot(_key_stream_counts, self._key_id)


async def try_acquire_stream_bulkhead(cfg, *, app_id: int, key_id: int) -> Optional[StreamBulkhead]:
    """Returns a `StreamBulkhead` on success, or `None` if any cap is exhausted."""
    if not _try_reserve_slot(_app_stream_counts, app_id, cfg.max_concurrent_streams_per_app):
        return None
    if not _try_reserve_slot(_key_stream_counts, key_id, cfg.max_concurrent_streams_per_key):
        _release_slot(_app_stream_counts, app_id)
        return None
    semaphore = _get_worker_stream_semaphore(cfg.max_concurrent_streams_worker)
    if not await _acquire_worker_slot(semaphore):
        _release_slot(_app_stream_counts, app_id)
        _release_slot(_key_stream_counts, key_id)
        return None
    return StreamBulkhead(worker_acquired=True, app_id=app_id, key_id=key_id)


# ---------------------------------------------------------------------------
# RB-2: wall-clock cap + liveness
# ---------------------------------------------------------------------------


async def bounded_sse_iterator(
    inner: AsyncGenerator[Dict[str, Any], None],
    *,
    rt: Any,
    owner: str,
    task_id: Optional[str],
    stream_max_seconds: float,
    liveness_interval_seconds: float,
    event_poll_seconds: float,
    bulkhead: Optional[StreamBulkhead],
    request_log: A2ARequestLog,
    emit_log: Callable[[], None],
) -> AsyncGenerator[Dict[str, Any], None]:
    """Wraps the SDK's own SSE body iterator (RB-2/RB-3/RB-4).

    - RB-2: ends the stream once `stream_max_seconds` elapses, or once a
      periodic `store.get` liveness check finds the task missing or terminal
      (the SDK's own remote-tail poll has no such bound). MEDIUM-10 (fix
      round 1): on a terminal/missing finding, this does **not** cut the
      stream off mid-flight -- it drains for
      `2 * event_poll_seconds + 1` more seconds, forwarding any events still
      arriving (the owning worker may have written a few more updates
      between the liveness check and the terminal write becoming visible
      here), before actually closing.
    - RB-3: releases `bulkhead`'s slots exactly once, on every exit path,
      including a client disconnect (`GeneratorExit`).
    - RB-4: sanitizes any in-flight `-32603` error event before it reaches
      the caller.
    - LOW-2: `emit_log` (required) is called synchronously from `finally`,
      right after the bulkhead release -- never relying on `resp.background`
      alone, which `sse_starlette` skips on a `SendTimeoutError`, an inner
      exception, or a shutdown cancel. Best-effort: any exception it raises
      is caught and logged, never allowed to interrupt teardown.

    MEDIUM-9 (fix round 1): the outcome is finalized and `bulkhead` released
    synchronously, as the *first* thing `finally` does -- before any
    cleanup `await` -- so a request-log emission racing this teardown never
    observes a stale "still open" state. The cleanup awaits themselves
    (cancelling/awaiting `pending`, closing `inner`) are wrapped in a
    shielded, time-boxed scope (`anyio.CancelScope(shield=True)` +
    `move_on_after`) so a *second* cancellation landing on this same
    teardown (e.g. the worker shutting down while a client is also
    disconnecting) can never abandon it partway, nor hang it forever.
    """
    deadline = time.monotonic() + stream_max_seconds
    next_liveness_check = time.monotonic() + liveness_interval_seconds
    pending = asyncio.ensure_future(inner.__anext__())
    outcome = "stream_ended"
    liveness_timeout = min(2.0, liveness_interval_seconds) if liveness_interval_seconds > 0 else 2.0

    async def _drain_remaining(grace_seconds: float) -> AsyncGenerator[Dict[str, Any], None]:
        """MEDIUM-10: forwards any events still arriving for `grace_seconds`
        after a terminal/missing finding, instead of cutting the stream."""
        nonlocal pending
        drain_deadline = time.monotonic() + grace_seconds
        while True:
            remaining = drain_deadline - time.monotonic()
            if remaining <= 0:
                return
            done, _ = await asyncio.wait({pending}, timeout=remaining)
            if pending not in done:
                return
            try:
                item = pending.result()
            except StopAsyncIteration:
                return
            except Exception:
                logger.exception("a2a.stream.drain_error task_id=%s", task_id)
                return
            yield_item = sanitize_sse_item(item)
            yield yield_item
            pending = asyncio.ensure_future(inner.__anext__())

    try:
        while True:
            now = time.monotonic()
            remaining_wall = deadline - now
            if remaining_wall <= 0:
                logger.info("a2a.stream.wall_clock_cap_reached task_id=%s", task_id)
                outcome = "stream_wall_clock_cap"
                return
            wait_timeout = max(0.01, min(remaining_wall, next_liveness_check - now))
            done, _ = await asyncio.wait({pending}, timeout=max(0.0, wait_timeout))

            if pending in done:
                try:
                    item = pending.result()
                except StopAsyncIteration:
                    return
                found_task_id = extract_task_id_from_sse_item(item)
                if found_task_id:
                    task_id = found_task_id
                yield sanitize_sse_item(item)
                pending = asyncio.ensure_future(inner.__anext__())
                continue

            now = time.monotonic()
            if now >= deadline:
                logger.info("a2a.stream.wall_clock_cap_reached task_id=%s", task_id)
                outcome = "stream_wall_clock_cap"
                return
            if now >= next_liveness_check:
                next_liveness_check = now + liveness_interval_seconds
                if task_id:
                    try:
                        stored = await asyncio.wait_for(
                            rt.store.get(task_id, context_for_owner(owner)), timeout=liveness_timeout
                        )
                    except asyncio.TimeoutError:
                        # MEDIUM-10: a slow/contended store read is not
                        # itself evidence the task is gone -- just skip this
                        # round and try again at the next interval.
                        logger.info("a2a.stream.liveness_check_timeout task_id=%s", task_id)
                        continue
                    except Exception:
                        logger.exception("a2a.stream.liveness_check_error task_id=%s", task_id)
                        continue
                    if stored is None:
                        logger.info("a2a.stream.task_missing_draining task_id=%s", task_id)
                        outcome = "stream_task_missing"
                        async for drained in _drain_remaining(2 * event_poll_seconds + 1):
                            yield drained
                        return
                    if stored.task.status.state in TERMINAL_TASK_STATES:
                        logger.info("a2a.stream.task_terminal_draining task_id=%s", task_id)
                        outcome = "stream_task_terminal"
                        async for drained in _drain_remaining(2 * event_poll_seconds + 1):
                            yield drained
                        return
    except (GeneratorExit, asyncio.CancelledError):
        # A client disconnect reaches the generator as CancelledError.
        outcome = "client_disconnect"
        raise
    finally:
        # MEDIUM-9: finalize bookkeeping synchronously, first -- never after
        # a cleanup `await` that could itself be cancelled or time out.
        if bulkhead is not None:
            bulkhead.release()
        if request_log.outcome is None:
            request_log.outcome = outcome
        try:
            emit_log()
        except Exception:
            logger.exception("a2a.stream.emit_log_error task_id=%s", task_id)

        with anyio.CancelScope(shield=True), anyio.move_on_after(_TEARDOWN_BUDGET_SECONDS):
            if not pending.done():
                pending.cancel()
            with contextlib.suppress(StopAsyncIteration, asyncio.CancelledError, Exception):
                await pending
            try:
                await inner.aclose()
            except Exception:
                logger.exception("a2a.stream.inner_close_error task_id=%s", task_id)


__all__ = [
    "StreamBulkhead",
    "try_acquire_stream_bulkhead",
    "bounded_sse_iterator",
    "reset_for_tests",
]
