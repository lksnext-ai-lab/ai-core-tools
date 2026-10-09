"""The DBOS-side outbox reconciler and queue helpers in ``scheduling.output_delivery``."""

import contextlib
from datetime import datetime

import pytest

from models.output_delivery import OutputDelivery, OutputDeliveryAttempt, ScheduledTaskOutputBinding
from scheduling import output_delivery

from .factories import make_destination, make_run, make_task

PAST = datetime(2020, 1, 1)
FUTURE = datetime(2999, 1, 1)


@pytest.fixture
def sessions(outbox, monkeypatch):
    monkeypatch.setattr(output_delivery, "SessionLocal", outbox)
    with outbox() as db:
        db.add_all([make_task(), make_run(), make_destination(1), make_destination(2, provider_key="webhook")])
        db.add_all([ScheduledTaskOutputBinding(id=1, scheduled_task_id=1, destination_id=1),
                    ScheduledTaskOutputBinding(id=2, scheduled_task_id=1, destination_id=2)])
        db.commit()
    return outbox


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(output_delivery, "enqueue_delivery", lambda delivery_id, generation: calls.append((delivery_id, generation)))
    return calls


def _add(sessions, *, binding_id=1, event_type="succeeded", **fields):
    with sessions() as db:
        delivery = OutputDelivery(run_id=1, binding_id=binding_id, destination_id=binding_id, event_type=event_type, **fields)
        db.add(delivery)
        db.commit()
        return delivery.id


def _get(sessions, delivery_id):
    with sessions() as db:
        delivery = db.get(OutputDelivery, delivery_id)
        return delivery, list(delivery.attempts)


@pytest.mark.asyncio
async def test_due_deliveries_are_queued_and_retries_get_a_new_generation(sessions, queued):
    pending = _add(sessions, status="pending")
    retry = _add(sessions, binding_id=2, status="retry_wait", next_attempt_at=PAST, dispatch_generation=3)
    not_due = _add(sessions, event_type="later", status="retry_wait", next_attempt_at=FUTURE)

    assert await output_delivery._reconcile_pending_deliveries() == 2

    assert queued == [(pending, 0), (retry, 4)]
    assert _get(sessions, retry)[0].status == "pending"
    assert _get(sessions, not_due)[0].status == "retry_wait"


@pytest.mark.asyncio
async def test_expired_deliveries_fail_instead_of_sending(sessions, queued):
    delivery_id = _add(sessions, status="pending", expires_at=PAST)
    assert await output_delivery._reconcile_pending_deliveries() == 0
    delivery, _ = _get(sessions, delivery_id)
    assert delivery.status == "failed" and "expired" in delivery.error_summary and queued == []


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot, attempts, expected", [
    ({"provider_key": "teams_workflow"}, 1, "unknown"),
    ({"provider_key": "webhook", "receiver_deduplicates": True}, 1, "retry_wait"),
    ({"provider_key": "webhook", "receiver_deduplicates": True}, 5, "unknown"),
])
async def test_abandoned_in_flight_deliveries_are_classified(sessions, queued, snapshot, attempts, expected):
    delivery_id = _add(sessions, status="sending", lease_until=PAST, attempt_count=attempts, destination_snapshot=snapshot)
    with sessions() as db:
        db.add(OutputDeliveryAttempt(delivery_id=delivery_id, attempt_number=attempts, status="sending"))
        db.commit()

    await output_delivery._reconcile_pending_deliveries()

    delivery, delivery_attempts = _get(sessions, delivery_id)
    assert delivery.status == expected and delivery_attempts[-1].status == expected
    assert delivery.lease_until is None and delivery_attempts[-1].finished_at is not None
    assert (delivery.next_attempt_at is not None) is (expected == "retry_wait")
    assert queued == []


@pytest.mark.asyncio
async def test_queue_failures_and_spool_cleanup_errors_do_not_abort_the_sweep(sessions, monkeypatch):
    _add(sessions, status="pending")

    def unavailable(delivery_id, generation):
        raise RuntimeError("already queued")

    def broken_cleanup(db):
        raise OSError("disk unavailable")

    monkeypatch.setattr(output_delivery, "enqueue_delivery", unavailable)
    monkeypatch.setattr(output_delivery, "cleanup_spool_files", broken_cleanup)
    assert await output_delivery._reconcile_pending_deliveries() == 0


@pytest.mark.asyncio
async def test_database_failures_are_contained(monkeypatch, queued):
    class BrokenSession:
        def query(self, *args):
            raise RuntimeError("database unavailable")

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(output_delivery, "SessionLocal", BrokenSession)
    assert await output_delivery._reconcile_pending_deliveries() == 0
    assert queued == []


class FakeDbos:
    def __init__(self):
        self.enqueued = []

    def enqueue_workflow(self, queue, workflow, *args):
        self.enqueued.append((queue, workflow, args))


def test_enqueue_delivery_uses_a_deterministic_workflow_id(monkeypatch):
    workflow_ids = []
    fake = FakeDbos()

    @contextlib.contextmanager
    def set_workflow_id(workflow_id):
        workflow_ids.append(workflow_id)
        yield

    monkeypatch.setattr(output_delivery, "DBOS", fake)
    monkeypatch.setattr(output_delivery, "SetWorkflowID", set_workflow_id)

    assert output_delivery.enqueue_delivery(5, 2) == "output-delivery-5-g2"
    assert workflow_ids == ["output-delivery-5-g2"]
    assert fake.enqueued == [(output_delivery.OUTPUT_QUEUE, output_delivery.output_delivery_workflow, (5, 2))]


def test_enqueue_delivery_requires_dbos(monkeypatch):
    monkeypatch.setattr(output_delivery, "DBOS", None)
    with pytest.raises(RuntimeError, match="not available"):
        output_delivery.enqueue_delivery(5, 2)
    # The best-effort fast path leaves the row for the reconciler instead of raising.
    output_delivery.queue_delivery_after_commit(5, 2)
