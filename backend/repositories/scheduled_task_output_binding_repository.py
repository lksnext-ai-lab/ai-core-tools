"""Data access for scheduled-task output bindings. Never commits."""

from collections.abc import Collection

from models.output_delivery import OutputDestination, ScheduledTaskOutputBinding
from sqlalchemy.orm import Session


class ScheduledTaskOutputBindingRepository:
    """Stateless repository for ScheduledTaskOutputBinding."""

    @staticmethod
    def list_by_task(db: Session, task_id: int) -> list[ScheduledTaskOutputBinding]:
        """Every binding of a task, enabled or not."""
        return db.query(ScheduledTaskOutputBinding).filter_by(scheduled_task_id=task_id).all()

    @staticmethod
    def list_enabled_with_enabled_destination(
        db: Session, task_id: int, app_id: int,
    ) -> list[ScheduledTaskOutputBinding]:
        """Enabled bindings of a task whose destination is enabled and in the app."""
        return db.query(ScheduledTaskOutputBinding).join(OutputDestination).filter(
            ScheduledTaskOutputBinding.scheduled_task_id == task_id,
            ScheduledTaskOutputBinding.enabled.is_(True),
            OutputDestination.enabled.is_(True),
            OutputDestination.app_id == app_id,
        ).all()

    @staticmethod
    def list_enabled_attachment_candidates(
        db: Session, task_id: int, app_id: int, provider_keys: Collection[str],
    ) -> list[ScheduledTaskOutputBinding]:
        """Enabled bindings to enabled destinations of the given providers."""
        return db.query(ScheduledTaskOutputBinding).join(OutputDestination).filter(
            ScheduledTaskOutputBinding.scheduled_task_id == task_id,
            ScheduledTaskOutputBinding.enabled.is_(True),
            OutputDestination.enabled.is_(True),
            OutputDestination.provider_key.in_(provider_keys),
            OutputDestination.app_id == app_id,
        ).all()

    @staticmethod
    def list_enabled_view(db: Session, task_id: int, app_id: int) -> list[ScheduledTaskOutputBinding]:
        """Enabled bindings of a task in the app, ordered by destination name."""
        return (
            db.query(ScheduledTaskOutputBinding).join(OutputDestination)
            .filter(ScheduledTaskOutputBinding.scheduled_task_id == task_id,
                    OutputDestination.app_id == app_id, ScheduledTaskOutputBinding.enabled.is_(True))
            .order_by(OutputDestination.name).all()
        )

    @staticmethod
    def add(db: Session, binding: ScheduledTaskOutputBinding) -> None:
        """Add a binding to the session."""
        db.add(binding)
