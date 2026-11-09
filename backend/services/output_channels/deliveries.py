"""Read access to the deliveries of a scheduled task run."""

from typing import Any

from models.output_delivery import OutputDelivery
from models.scheduled_task import ScheduledTask
from repositories.output_delivery_repository import OutputDeliveryRepository
from services.output_channels.dto import delivery_dto
from sqlalchemy.orm import Session


def find_task_delivery(db: Session, *, app_id: int, task_id: int, run_id: int, delivery_id: int) -> OutputDelivery | None:
    """The delivery when its run belongs to the task and the task to the app, else None."""
    return OutputDeliveryRepository.get_scoped(
        db, app_id=app_id, task_id=task_id, run_id=run_id, delivery_id=delivery_id,
    )


def list_run_deliveries(db: Session, task: ScheduledTask, run_id: int) -> list[dict[str, Any]] | None:
    """Delivery dtos of a run ordered by id, or None when the run does not belong to the task."""
    run = next((item for item in task.runs if item.id == run_id), None)
    if not run:
        return None
    return [delivery_dto(item) for item in OutputDeliveryRepository.list_by_run(db, run_id)]
