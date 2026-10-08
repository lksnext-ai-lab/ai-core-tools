"""Unit tests for `services.a2a_server.executor` internals (fix round 2, item 2).

No DB, no SDK runtime: `_drain`/`_await_pending_to_completion` are driven
directly against a hand-written fake async generator and minimal
duck-typed `TaskUpdater`/`ResponseArtifactMapper` stand-ins, so this file
can run as a pure `tests/unit` test.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

import services.a2a_server.executor as executor_module
from services.a2a_server.executor import MattinAgentExecutor, _TurnState


class _FakeUpdater:
    """Only exposes what `_drain` touches: `.task_id` and the two write calls."""

    task_id = "fake-task-id"

    async def add_artifact(self, *args, **kwargs) -> None:  # pragma: no cover - not exercised here
        pass

    async def update_status(self, *args, **kwargs) -> None:  # pragma: no cover - not exercised here
        pass


class _FakeMapper:
    """Ignores every event; never produces a terminal action."""

    async def apply(self, event, now):
        return []

    def flush_due(self, now):
        return None


class TestDoubleCancelDuringTeardown:
    """Fix round 2, item 2: a generator whose own cancellation handling is
    itself slow (``await asyncio.sleep(0.3)`` in its ``except
    CancelledError`` clause) must still be waited out correctly even if the
    task running `_drain` is cancelled a *second* time while that slow
    cleanup is in flight -- `_await_pending_to_completion`'s `continue` (not
    `return`) on a `CancelledError` from its own shielded wait is what makes
    that safe. If that `continue` were a `return` instead, this test fails:
    `_drain` would return/raise while `pending` (the task driving the fake
    generator) is still mid-cleanup, and the caller's `aclosing`/`aclose()`
    right after would then race a still-executing generator frame.
    """

    @pytest.mark.asyncio
    async def test_second_cancellation_during_slow_cleanup_does_not_abandon_the_generator(self):
        cleanup_sentinel = {"done": False}

        async def _gen():
            try:
                yield object()
                await asyncio.sleep(10)  # pragma: no cover - cancelled before this resumes
            except asyncio.CancelledError:
                await asyncio.sleep(0.3)
                cleanup_sentinel["done"] = True
                raise

        agen = _gen()
        executor = MattinAgentExecutor()
        turn_state = _TurnState()

        drain_task = asyncio.ensure_future(
            executor._drain(
                agen, _FakeUpdater(), _FakeMapper(), keepalive_seconds=5.0, coalesce_seconds=0.0,
                turn_state=turn_state,
            )
        )

        # Let `_drain` consume the first (only) yielded event and move on to
        # awaiting the second `__anext__()` call, which drives the fake
        # generator into `asyncio.sleep(10)`.
        await asyncio.sleep(0.05)
        drain_task.cancel()

        # While the fake generator's own cleanup is still mid-flight (its
        # `asyncio.sleep(0.3)`), cancel the task running `_drain` a second
        # time -- this is the scenario `_await_pending_to_completion` must
        # survive via `continue`, not `return`.
        await asyncio.sleep(0.05)
        drain_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await drain_task

        assert cleanup_sentinel["done"] is True, (
            "the fake generator's slow cleanup must have been allowed to finish "
            "before _drain's teardown gave up"
        )

        # Exactly what `execute()`'s `contextlib.aclosing.__aexit__` does
        # right after `_drain` returns/raises. If the generator were still
        # mid-frame (the `continue`-vs-`return` regression this test guards
        # against), this would raise `RuntimeError: aclose(): asynchronous
        # generator is already running` instead of completing cleanly.
        await agen.aclose()


class TestBoundedTeardownWait:
    """Fix round 2, item 1: `_await_pending_to_completion` must not wait
    forever for a generator whose own cancellation cleanup hangs -- it gives
    up after `_TEARDOWN_BUDGET_SECONDS`, logs an ERROR (task_id only), and
    returns, leaving `pending` abandoned rather than blocking this turn's
    teardown indefinitely.
    """

    @pytest.mark.asyncio
    async def test_gives_up_after_the_budget_and_logs_an_error(self, monkeypatch):
        monkeypatch.setattr(executor_module, "_TEARDOWN_BUDGET_SECONDS", 0.2)

        # The project's `utils.logger.get_logger` sets `propagate = False` on
        # every logger it builds (to avoid double-logging through a stray
        # root handler), which defeats pytest's `caplog` fixture (it relies
        # on propagation unless a handler is attached to this *exact*
        # logger). Spying directly on `logger.error` is simpler and immune
        # to that logging-config detail.
        error_calls: list = []
        monkeypatch.setattr(
            executor_module.logger, "error", lambda *args, **kwargs: error_calls.append(args)
        )

        async def _gen():
            try:
                yield object()
                await asyncio.sleep(10)  # pragma: no cover - cancelled before this resumes
            except asyncio.CancelledError:
                # Hangs well past the (patched) teardown budget.
                await asyncio.sleep(5)
                raise  # pragma: no cover - the budget expires first

        agen = _gen()
        executor = MattinAgentExecutor()
        turn_state = _TurnState()

        drain_task = asyncio.ensure_future(
            executor._drain(
                agen, _FakeUpdater(), _FakeMapper(), keepalive_seconds=5.0, coalesce_seconds=0.0,
                turn_state=turn_state,
            )
        )
        await asyncio.sleep(0.05)
        drain_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(drain_task, timeout=2.0)

        assert any(
            args and "a2a.executor.drain_teardown_timeout" in args[0] and _FakeUpdater.task_id in args
            for args in error_calls
        ), f"expected a drain_teardown_timeout ERROR log naming the task_id; got {error_calls!r}"

        # `_await_pending_to_completion` gave up on `pending` (the task
        # driving `agen.__anext__()`) after the (patched) teardown budget,
        # while the fake generator's own `except CancelledError` clause was
        # still mid-`asyncio.sleep(5)` -- so that task is left abandoned,
        # not-done, and never referenced by this test again. Left alone, it
        # would only finish (and be garbage-collected) well after this test
        # returns, which is exactly the "Task was destroyed but it is
        # pending" warning this regression test guards against. Cancelling
        # it again interrupts that `asyncio.sleep(5)` immediately (a second
        # `cancel()` delivers `CancelledError` at the task's current
        # suspension point right away, it does not wait out the sleep), so
        # awaiting it here is fast and leaves no pending task at loop close.
        current = asyncio.current_task()
        leftover = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
        for task in leftover:
            task.cancel()
        for task in leftover:
            with contextlib.suppress(asyncio.CancelledError):
                await task
