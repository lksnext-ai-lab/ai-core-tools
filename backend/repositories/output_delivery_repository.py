"""Data access for output deliveries and attempts. Never commits."""

from collections.abc import Collection
from datetime import datetime

from models.output_delivery import (
    OutputDelivery,
    OutputDeliveryAttempt,
    OutputDestination,
    ScheduledTaskOutputBinding,
)
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement


def _body_needed_clause(now: datetime, statuses: Collection[str]) -> ColumnElement[bool]:
    """Clause for deliveries that can still send and therefore need their prepared body."""
    return and_(
        OutputDelivery.status.in_(statuses),
        or_(OutputDelivery.expires_at.is_(None), OutputDelivery.expires_at > now),
    )


class OutputDeliveryRepository:
    """Stateless repository for OutputDelivery and OutputDeliveryAttempt."""

    @staticmethod
    def get_for_update(db: Session, delivery_id: int) -> OutputDelivery | None:
        """Row-lock a delivery by id."""
        return db.query(OutputDelivery).filter(OutputDelivery.id == delivery_id).with_for_update().one_or_none()

    @staticmethod
    def get_attempt(db: Session, attempt_id: int) -> OutputDeliveryAttempt | None:
        """Fetch an attempt by id."""
        return db.query(OutputDeliveryAttempt).filter_by(id=attempt_id).one_or_none()

    @staticmethod
    def find_existing(db: Session, run_id: int, binding_id: int, event_type: str) -> OutputDelivery | None:
        """The delivery already created for a run/binding/event, if any."""
        return db.query(OutputDelivery).filter_by(
            run_id=run_id, binding_id=binding_id, event_type=event_type,
        ).one_or_none()

    @staticmethod
    def list_by_run(db: Session, run_id: int) -> list[OutputDelivery]:
        """Deliveries of a run ordered by id."""
        return db.query(OutputDelivery).filter_by(run_id=run_id).order_by(OutputDelivery.id).all()

    @staticmethod
    def get_scoped(db: Session, *, app_id: int, task_id: int, run_id: int, delivery_id: int) -> OutputDelivery | None:
        """A delivery only when its run belongs to the task and the task to the app."""
        return db.query(OutputDelivery).join(OutputDelivery.run).join(ScheduledTask).filter(
            OutputDelivery.id == delivery_id,
            ScheduledTask.app_id == app_id,
            ScheduledTask.id == task_id,
            OutputDelivery.run_id == run_id,
        ).one_or_none()

    @staticmethod
    def lock_due_for_reconcile(db: Session, now: datetime, limit: int = 200) -> list[OutputDelivery]:
        """Row-lock (SKIP LOCKED) deliveries that are pending, due for retry or with an expired lease."""
        return (
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
            .limit(limit)
            .with_for_update(skip_locked=True)
            .all()
        )

    @staticmethod
    def find_runs_missing_outbox(db: Session, limit: int = 100) -> list[ScheduledTaskRun]:
        """Succeeded, unreconciled runs with an enabled binding but no delivery rows."""
        return (
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
            .limit(limit)
            .all()
        )

    @staticmethod
    def cancel_pending_for_destination(db: Session, destination_id: int) -> None:
        """Bulk-cancel pending/retry_wait deliveries of a destination."""
        db.query(OutputDelivery).filter(
            OutputDelivery.destination_id == destination_id,
            OutputDelivery.status.in_(["pending", "retry_wait"]),
        ).update({OutputDelivery.status: "cancelled"}, synchronize_session=False)

    @staticmethod
    def release_unneeded_bodies(db: Session, now: datetime, statuses: Collection[str]) -> None:
        """Bulk-clear prepared bodies of deliveries that cannot send any more."""
        needed = _body_needed_clause(now, statuses)
        db.query(OutputDelivery).filter(
            ~needed,
            or_(OutputDelivery.request_body.is_not(None), OutputDelivery.request_body_path.is_not(None)),
        ).update(
            {OutputDelivery.request_body: None, OutputDelivery.request_body_path: None},
            synchronize_session=False,
        )

    @staticmethod
    def referenced_body_paths(db: Session) -> set[str]:
        """Non-empty spool paths referenced by delivery request bodies."""
        return {
            key for (key,) in db.query(OutputDelivery.request_body_path)
            .filter(OutputDelivery.request_body_path.is_not(None)).all() if key
        }

    @staticmethod
    def add(db: Session, delivery: OutputDelivery) -> None:
        """Add a delivery to the session."""
        db.add(delivery)

    @staticmethod
    def add_attempt(db: Session, attempt: OutputDeliveryAttempt) -> None:
        """Add an attempt to the session."""
        db.add(attempt)
