"""DBOS queue workers for the scheduled-task output outbox."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from db.database import SessionLocal
from repositories.output_delivery_repository import OutputDeliveryRepository
from services.output_channels import delivery_policy
from services.output_channels.delivery_factory import create_deliveries_for_run
from services.output_channels.delivery_processor import process_delivery
from services.output_channels.spool import cleanup_spool_files
from utils.clock import utcnow_naive

logger = logging.getLogger(__name__)

try:
    from dbos import DBOS, SetWorkflowID
except ImportError:
    DBOS = None
    SetWorkflowID = None

OUTPUT_QUEUE = "output-deliveries"
OUTPUT_RECONCILER_QUEUE = "output-delivery-reconciler"
OUTPUT_RECONCILER_SCHEDULE = "output-delivery-reconciler"
# A pending row untouched for this long is assumed to have lost its workflow.
STALE_PENDING_SECONDS = 300


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
        now = utcnow_naive()
        # Repair the exceptional case where a completed durable agent step was
        # persisted after an outbox transaction failure.
        missing_outbox_runs = OutputDeliveryRepository.find_runs_missing_outbox(db, limit=100)
        for run in missing_outbox_runs:
            run_id = run.id
            try:
                with db.begin_nested():
                    from services.output_channels.attachments import prepare_run_attachments
                    artifacts, attachment_error = await prepare_run_attachments(db, task=run.task, run=run)
                    # Multipart bodies are written off the event loop; the session
                    # is only used by the thread while this coroutine awaits it.
                    await asyncio.to_thread(
                        create_deliveries_for_run,
                        db, task=run.task, run=run,
                        artifacts=artifacts, attachment_error=attachment_error,
                    )
                    run.outputs_reconciled = True
            except Exception:
                logger.exception("Could not repair output deliveries for scheduled task run %s", run_id)
        rows = OutputDeliveryRepository.lock_due_for_reconcile(db, now, limit=200)
        for item in rows:
            if item.expires_at and item.expires_at <= now and item.status != "sending":
                item.status = "failed"
                item.error_summary = "Delivery expired before it was sent."
                continue
            if item.status == "sending":
                snapshot = item.destination_snapshot or {}
                retry_deduplicated = (
                    delivery_policy.receiver_can_deduplicate(snapshot.get("provider_key"), snapshot)
                    and item.attempt_count < 5
                )
                item.status = "retry_wait" if retry_deduplicated else "unknown"
                item.error_summary = (
                    "Webhook worker stopped during an idempotent request; retry scheduled."
                    if retry_deduplicated else
                    "Worker stopped while the external request was in flight; verify receipt before resending."
                )
                if retry_deduplicated:
                    item.next_attempt_at = now + timedelta(seconds=30)
                item.lease_until = None
                if item.attempts:
                    attempt = item.attempts[-1]
                    attempt.status = item.status
                    attempt.finished_at = now
                    attempt.error_summary = item.error_summary
                continue
            if item.status == "retry_wait":
                if item.next_attempt_at and item.next_attempt_at > now:
                    continue
                item.dispatch_generation += 1
                item.next_attempt_at = None
                item.status = "pending"
            elif item.updated_at and item.updated_at <= now - timedelta(seconds=STALE_PENDING_SECONDS):
                # DBOS never re-runs a finished workflow id, so a dispatch that
                # failed before claiming the row would leave it pending until it
                # expires. A new generation gets a new workflow id; a still-queued
                # old one becomes a no-op because process_delivery checks it.
                item.dispatch_generation += 1
            enqueue.append((item.id, item.dispatch_generation))
        db.commit()
        try:
            await asyncio.to_thread(cleanup_spool_files, db)
        except Exception:
            logger.exception("Could not clean expired webhook spool files")
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
