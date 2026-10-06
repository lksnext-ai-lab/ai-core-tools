"""DBOS queue workers for the scheduled-task output outbox."""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_

from db.database import SessionLocal
from models.output_delivery import OutputDelivery, OutputDeliveryAttempt, OutputDestination, ScheduledTaskOutputBinding
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from output.service import create_deliveries_for_run
from output.service import process_delivery

logger = logging.getLogger(__name__)

try:
    from dbos import DBOS, SetWorkflowID
except ImportError:
    DBOS = None
    SetWorkflowID = None

OUTPUT_QUEUE = "output-deliveries"
OUTPUT_RECONCILER_QUEUE = "output-delivery-reconciler"
OUTPUT_RECONCILER_SCHEDULE = "output-delivery-reconciler"


def enqueue_delivery(delivery_id: int, generation: int) -> str:
    if DBOS is None:
        raise RuntimeError("DBOS output delivery is not available")
    workflow_id = f"output-delivery-{delivery_id}-g{generation}"
    with SetWorkflowID(workflow_id):
        handle = DBOS.enqueue_workflow(OUTPUT_QUEUE, output_delivery_workflow, delivery_id, generation)
    return workflow_id


async def _reconcile_pending_deliveries() -> int:
    db = SessionLocal()
    enqueue: list[tuple[int, int]] = []
    try:
        now = datetime.utcnow()
        # Repair the exceptional case where a completed durable agent step was
        # persisted after an outbox transaction failure.
        missing_outbox_runs = (
            db.query(ScheduledTaskRun)
            .join(ScheduledTask)
            .join(ScheduledTaskOutputBinding, ScheduledTaskOutputBinding.scheduled_task_id == ScheduledTask.id)
            .join(OutputDestination, OutputDestination.id == ScheduledTaskOutputBinding.destination_id)
            .filter(
                ScheduledTaskRun.status == "succeeded",
                ScheduledTaskRun.outputs_reconciled.is_(False),
                ScheduledTaskOutputBinding.enabled.is_(True),
                OutputDestination.enabled.is_(True),
                ~ScheduledTaskRun.output_deliveries.any(),
            )
            .order_by(ScheduledTaskRun.id)
            .limit(100)
            .all()
        )
        for run in missing_outbox_runs:
            run_id = run.id
            try:
                with db.begin_nested():
                    create_deliveries_for_run(db, task=run.task, run=run)
                    run.outputs_reconciled = True
            except Exception:
                logger.exception("Could not repair output deliveries for scheduled task run %s", run_id)
        rows = (
            db.query(OutputDelivery)
            .filter(or_(
                OutputDelivery.status == "pending",
                and_(
                    OutputDelivery.status == "retry_wait",
                    or_(OutputDelivery.next_attempt_at.is_(None), OutputDelivery.next_attempt_at <= now),
                ),
                and_(
                    OutputDelivery.status == "sending",
                    or_(OutputDelivery.lease_until.is_(None), OutputDelivery.lease_until <= now),
                ),
            ))
            .order_by(OutputDelivery.id)
            .limit(200)
            .with_for_update(skip_locked=True)
            .all()
        )
        for item in rows:
            if item.expires_at and item.expires_at <= now and item.status != "sending":
                item.status = "failed"
                item.error_summary = "Delivery expired before it was sent."
                continue
            if item.status == "sending":
                item.status = "unknown"
                item.error_summary = "Worker stopped while the Teams request was in flight; verify the channel before resending."
                item.lease_until = None
                if item.attempts:
                    attempt = item.attempts[-1]
                    attempt.status = "unknown"
                    attempt.finished_at = now
                    attempt.error_summary = item.error_summary
                continue
            if item.status == "retry_wait":
                if item.next_attempt_at and item.next_attempt_at > now:
                    continue
                item.dispatch_generation += 1
                item.next_attempt_at = None
                item.status = "pending"
            enqueue.append((item.id, item.dispatch_generation))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not reconcile scheduled-task output deliveries")
        return 0
    finally:
        db.close()

    queued = 0
    for delivery_id, generation in enqueue:
        try:
            enqueue_delivery(delivery_id, generation)
            queued += 1
        except Exception as exc:
            # DB outbox remains pending and will be picked up on the next sweep.
            logger.info("Output delivery %s generation %s is already queued or unavailable: %s", delivery_id, generation, type(exc).__name__)
    return queued


if DBOS is not None:
    @DBOS.step(retries_allowed=False)
    async def process_output_delivery_step(delivery_id: int, generation: int) -> None:
        await process_delivery(delivery_id, generation)

    @DBOS.workflow(max_recovery_attempts=1)
    async def output_delivery_workflow(delivery_id: int, generation: int) -> None:
        await process_output_delivery_step(delivery_id, generation)

    @DBOS.workflow(max_recovery_attempts=1)
    async def output_delivery_reconciler(scheduled_time: datetime, context: Any = None) -> None:
        await _reconcile_pending_deliveries()
else:
    async def process_output_delivery_step(delivery_id: int, generation: int) -> None:
        raise RuntimeError("DBOS is not installed")

    async def output_delivery_workflow(delivery_id: int, generation: int) -> None:
        raise RuntimeError("DBOS is not installed")

    async def output_delivery_reconciler(scheduled_time: datetime, context: Any = None) -> None:
        raise RuntimeError("DBOS is not installed")


def queue_delivery_after_commit(delivery_id: int, generation: int) -> None:
    """Best-effort fast path; the scheduled reconciler closes the commit/enqueue gap."""
    try:
        enqueue_delivery(delivery_id, generation)
    except Exception as exc:
        logger.info("Output delivery %s will be recovered by the reconciler: %s", delivery_id, type(exc).__name__)
