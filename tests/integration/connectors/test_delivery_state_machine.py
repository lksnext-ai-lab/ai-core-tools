"""Characterization of the outbox state machine against real PostgreSQL.

These tests document CURRENT behavior of ``process_delivery`` and the DBOS
reconciler (``_reconcile_pending_deliveries``); they do not fix anything.
They use only ``scheduling.output_delivery`` entry points and the models so
they survive the move of ``backend/output/``.

Concurrency tests use genuinely separate connections. Lock waits are bounded
by a DB-side ``lock_timeout`` (conftest ``db_lock_timeout``, applied to every
connection incl. the code under test), because a blocked psycopg2 call cannot
be interrupted by ``asyncio.wait_for``; threads are daemons joined with a
timeout and row locks are always released in ``finally``.

NOT xdist-safe: the reconciler tests sweep the whole outbox table and the
fixture commits real rows, so run this directory in a single process.
"""

import asyncio
import threading

import httpx
import pytest
from db.database import SessionLocal
from models.output_delivery import OutputDelivery, OutputDeliveryAttempt
from scheduling import output_delivery
from sqlalchemy import event

from tests.integration.connectors.helpers import (
    fetch_delivery,
    future,
    past,
    wait_for_lock_waiter,
)

pytestmark = pytest.mark.integration

STALE_SENDING_WEBHOOK_MSG = "Webhook worker stopped during an idempotent request; retry scheduled."
STALE_SENDING_UNKNOWN_MSG = "Worker stopped while the external request was in flight; verify receipt before resending."


def _lock_row(session, delivery_id: int) -> OutputDelivery:
    return session.query(OutputDelivery).filter_by(id=delivery_id).with_for_update().one()


class TestProcessDeliveryRowLock:
    async def test_second_worker_skips_a_delivery_already_sending(self, committed_outbox, webhook_http):
        """Lease-guard test (NOT a row-lock test).

        ``process_delivery`` claims the row and commits ``sending`` + a lease before
        its first await, so two coroutines on one loop never overlap inside the
        database: the second one exits on the "sending with a live lease" guard.
        The ``FOR UPDATE`` lock itself is pinned by the two thread-based tests below.
        """
        delivery_id = committed_outbox.make_delivery("webhook", status="pending")
        release = asyncio.Event()

        async def handler(request: httpx.Request) -> httpx.Response:
            # Block the first sender until the second worker has finished.
            await asyncio.wait_for(release.wait(), timeout=10)
            return httpx.Response(200, json={"ok": True})

        webhook_http.handler = handler

        async def first():
            await asyncio.wait_for(output_delivery.process_delivery(delivery_id, 0), timeout=20)

        async def second():
            try:
                await asyncio.wait_for(output_delivery.process_delivery(delivery_id, 0), timeout=20)
            finally:
                release.set()

        await asyncio.gather(first(), second())

        assert len(webhook_http.requests) == 1
        row = fetch_delivery(delivery_id)
        assert len(row["attempts"]) == 1
        assert row["attempts"][0]["status"] == "accepted"
        assert row["status"] == "accepted"
        assert row["attempt_count"] == 1

    def test_concurrent_workers_serialize_on_the_row_lock(self, committed_outbox, webhook_http):
        """Worker 1 is held inside its transaction (after SELECT ... FOR UPDATE, before
        the commit); worker 2 must WAIT on the lock, then find ``sending`` and skip.

        The hook is a SQLAlchemy ``init`` event on ``OutputDeliveryAttempt``: process_delivery
        builds the attempt between the claim and the commit, and the models module survives
        the later move of ``backend/output/`` (no name to repoint in step_003).
        """
        delivery_id = committed_outbox.make_delivery("webhook", status="pending")
        in_txn = threading.Event()
        release = threading.Event()
        first_caller = threading.Lock()
        claimed = []
        errors: list[BaseException] = []

        def hook(target, args, kwargs):
            if first_caller.acquire(blocking=False):
                claimed.append(threading.current_thread().name)
                in_txn.set()
                release.wait(timeout=20)

        def worker():
            try:
                asyncio.run(output_delivery.process_delivery(delivery_id, 0))
            except BaseException as exc:  # noqa: BLE001 - surfaced in the main thread
                errors.append(exc)

        w1 = threading.Thread(target=worker, name="worker-1", daemon=True)
        w2 = threading.Thread(target=worker, name="worker-2", daemon=True)
        event.listen(OutputDeliveryAttempt, "init", hook)
        try:
            w1.start()
            assert in_txn.wait(timeout=10), "worker 1 never reached the claim step"
            w2.start()
            assert wait_for_lock_waiter(), "worker 2 never waited on the row lock"
        finally:
            release.set()
            w1.join(timeout=15)
            if w2.ident is not None:
                w2.join(timeout=15)
            event.remove(OutputDeliveryAttempt, "init", hook)

        assert not w1.is_alive(), "worker 1 did not finish"
        assert not w2.is_alive(), "worker 2 did not finish"
        assert errors == []
        assert claimed == ["worker-1"]
        assert len(webhook_http.requests) == 1
        row = fetch_delivery(delivery_id)
        assert len(row["attempts"]) == 1
        assert row["status"] == "accepted"
        assert row["attempt_count"] == 1

    def test_blocked_by_external_for_update_lock(self, committed_outbox, webhook_http):
        """A real row lock held by another connection blocks the worker thread."""
        delivery_id = committed_outbox.make_delivery("webhook", status="pending")
        errors: list[BaseException] = []

        def run():
            try:
                asyncio.run(output_delivery.process_delivery(delivery_id, 0))
            except BaseException as exc:  # noqa: BLE001 - surfaced in the main thread
                errors.append(exc)

        holder = SessionLocal()
        thread = threading.Thread(target=run, daemon=True)
        try:
            _lock_row(holder, delivery_id)
            thread.start()
            assert wait_for_lock_waiter(), "process_delivery never waited for the FOR UPDATE lock"
            holder.query(OutputDelivery).filter_by(id=delivery_id).update({"status": "accepted"})
            holder.commit()
            thread.join(timeout=15)
            assert not thread.is_alive(), "worker did not resume after the lock was released"
        finally:
            holder.rollback()
            holder.close()
            if thread.ident is not None:
                thread.join(timeout=15)

        assert not thread.is_alive(), "worker thread is still running"
        assert errors == []
        assert webhook_http.requests == []
        row = fetch_delivery(delivery_id)
        assert row["status"] == "accepted"
        assert row["attempts"] == []
        assert row["attempt_count"] == 0


class TestReconcilerSkipLocked:
    def test_locked_row_is_skipped(self, committed_outbox, enqueued):
        locked_id = committed_outbox.make_delivery("webhook", status="pending", updated_at=past(1000))
        free_id = committed_outbox.make_delivery("webhook", status="pending", updated_at=past(1000))
        before = fetch_delivery(locked_id)

        holder = SessionLocal()
        thread = None
        result: list[int] = []
        errors: list[BaseException] = []
        try:
            _lock_row(holder, locked_id)
            # Run in a thread: the reconciler does blocking DB calls, so if SKIP LOCKED
            # regressed it would block on the held lock; the bounded join keeps the
            # test from hanging and the lock is released in `finally`.

            def run():
                try:
                    result.append(asyncio.run(output_delivery._reconcile_pending_deliveries()))
                except BaseException as exc:  # noqa: BLE001 - surfaced in the main thread
                    errors.append(exc)

            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            thread.join(timeout=5)
            assert not thread.is_alive(), "reconciler blocked on a locked row (SKIP LOCKED regression?)"
        finally:
            holder.rollback()
            holder.close()
            if thread is not None:
                thread.join(timeout=15)
        assert errors == []
        assert not thread.is_alive(), "reconciler thread is still running"
        assert result, errors

        queued_ids = {delivery_id for delivery_id, _ in enqueued}
        assert free_id in queued_ids
        assert locked_id not in queued_ids
        # A stale pending row gets a new dispatch generation (new workflow id).
        assert (free_id, 1) in enqueued
        assert fetch_delivery(free_id)["dispatch_generation"] == 1
        after = fetch_delivery(locked_id)
        assert after["dispatch_generation"] == before["dispatch_generation"] == 0
        assert after["status"] == "pending"
        assert after["updated_at"] == before["updated_at"]


# (kind, snapshot, fields, expected_status_process, expected_status_reconciler)
STALE_SENDING_CASES = [
    pytest.param(
        "webhook", {"receiver_deduplicates": True}, {"attempt_count": 1, "expires_at": future()},
        "retry_wait", "retry_wait", id="webhook-dedupe-retryable",
    ),
    pytest.param(
        "teams", {}, {"attempt_count": 1, "expires_at": future()},
        "unknown", "unknown", id="teams-unknown",
    ),
    pytest.param(
        "webhook", {"receiver_deduplicates": True}, {"attempt_count": 5, "expires_at": future()},
        "unknown", "unknown", id="webhook-dedupe-attempts-exhausted",
    ),
    pytest.param(
        "webhook", {"receiver_deduplicates": True}, {"attempt_count": 1, "expires_at": past()},
        # CB-3 (FR-15): este caso pasa a "unknown" en step_012. Today the two paths
        # DIVERGE: process_delivery honors expires_at, the reconciler ignores it.
        "unknown", "retry_wait", id="webhook-dedupe-expired-DIVERGENCE",
    ),
]


def _make_stale_sending(ob, kind, snapshot, fields):
    return ob.make_delivery(
        kind, status="sending", lease_until=past(60), snapshot=snapshot,
        attempts=[{"status": "sending"}], **fields,
    )


def _assert_stale_outcome(row, expected_status):
    assert row["status"] == expected_status
    assert row["lease_until"] is None
    expected_msg = STALE_SENDING_WEBHOOK_MSG if expected_status == "retry_wait" else STALE_SENDING_UNKNOWN_MSG
    assert row["error_summary"] == expected_msg
    if expected_status == "retry_wait":
        assert row["next_attempt_at"] is not None
    else:
        assert row["next_attempt_at"] is None
    (attempt,) = row["attempts"]
    assert attempt["status"] == expected_status
    assert attempt["finished_at"] is not None
    assert attempt["error_summary"] == expected_msg


class TestStaleSending:
    @pytest.mark.parametrize("kind, snapshot, fields, via_process, via_reconciler", STALE_SENDING_CASES)
    async def test_process_delivery_path(self, committed_outbox, webhook_http, kind, snapshot, fields, via_process, via_reconciler):
        delivery_id = _make_stale_sending(committed_outbox, kind, snapshot, fields)
        await asyncio.wait_for(output_delivery.process_delivery(delivery_id, 0), timeout=20)
        assert webhook_http.requests == []  # never reposted
        _assert_stale_outcome(fetch_delivery(delivery_id), via_process)

    @pytest.mark.parametrize("kind, snapshot, fields, via_process, via_reconciler", STALE_SENDING_CASES)
    async def test_reconciler_path(self, committed_outbox, enqueued, kind, snapshot, fields, via_process, via_reconciler):
        delivery_id = _make_stale_sending(committed_outbox, kind, snapshot, fields)
        await asyncio.wait_for(output_delivery._reconcile_pending_deliveries(), timeout=20)
        assert delivery_id not in {i for i, _ in enqueued}  # classified, not re-enqueued
        _assert_stale_outcome(fetch_delivery(delivery_id), via_reconciler)

    async def test_live_lease_is_left_alone(self, committed_outbox, webhook_http, enqueued):
        lease = future(120)
        delivery_id = committed_outbox.make_delivery(
            "webhook", status="sending", lease_until=lease, attempt_count=1, attempts=[{"status": "sending"}],
        )
        await asyncio.wait_for(output_delivery.process_delivery(delivery_id, 0), timeout=20)
        await asyncio.wait_for(output_delivery._reconcile_pending_deliveries(), timeout=20)
        row = fetch_delivery(delivery_id)
        assert row["status"] == "sending"
        assert row["lease_until"] == lease
        assert row["attempts"][0]["status"] == "sending"
        assert webhook_http.requests == []
        assert delivery_id not in {i for i, _ in enqueued}


def _bump_generation(delivery_id: int) -> None:
    with SessionLocal() as other:
        other.query(OutputDelivery).filter_by(id=delivery_id).update({"dispatch_generation": 1})
        other.commit()


class TestDispatchGeneration:
    async def test_old_generation_is_a_noop(self, committed_outbox, webhook_http):
        delivery_id = committed_outbox.make_delivery("webhook", status="pending", dispatch_generation=2)
        before = fetch_delivery(delivery_id)
        await asyncio.wait_for(output_delivery.process_delivery(delivery_id, 1), timeout=20)
        assert webhook_http.requests == []
        assert fetch_delivery(delivery_id) == before

    async def test_late_response_is_not_written(self, committed_outbox, webhook_http):
        delivery_id = committed_outbox.make_delivery("webhook", status="pending", dispatch_generation=0)

        async def handler(request: httpx.Request) -> httpx.Response:
            # While the request is in flight another actor bumps the generation.
            # Off-loop so a lock wait can never freeze the event loop.
            await asyncio.to_thread(_bump_generation, delivery_id)
            return httpx.Response(200, json={"ok": True})

        webhook_http.handler = handler
        await asyncio.wait_for(output_delivery.process_delivery(delivery_id, 0), timeout=20)

        assert len(webhook_http.requests) == 1
        row = fetch_delivery(delivery_id)
        assert row["dispatch_generation"] == 1
        assert row["status"] == "sending"
        assert row["receipt"] is None
        assert row["attempt_count"] == 1
        (attempt,) = row["attempts"]
        assert attempt["status"] == "sending"
        assert attempt["finished_at"] is None


class TestReconcilerExpiry:
    @pytest.mark.parametrize("status, extra", [
        ("pending", {}),
        ("retry_wait", {"next_attempt_at": past(10)}),
    ])
    async def test_expired_non_sending_fails(self, committed_outbox, enqueued, status, extra):
        delivery_id = committed_outbox.make_delivery("webhook", status=status, expires_at=past(60), **extra)
        await asyncio.wait_for(output_delivery._reconcile_pending_deliveries(), timeout=20)
        row = fetch_delivery(delivery_id)
        assert row["status"] == "failed"
        assert row["error_summary"] == "Delivery expired before it was sent."
        assert delivery_id not in {i for i, _ in enqueued}
