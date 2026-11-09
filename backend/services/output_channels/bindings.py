"""Scheduled-task to output-destination bindings."""

from typing import Any

from connectors import registry as connector_registry
from models.output_delivery import OutputDestination, ScheduledTaskOutputBinding
from models.scheduled_task import ScheduledTask
from repositories.scheduled_task_output_binding_repository import (
    ScheduledTaskOutputBindingRepository,
)
from services.output_channels.destinations import get_destination
from sqlalchemy.orm import Session


def replace_task_bindings(
    db: Session, *, task: ScheduledTask, app_id: int, bindings: list[dict[str, Any]], commit: bool = True,
) -> list[dict[str, Any]]:
    try:
        desired: dict[int, dict[str, Any]] = {}
        for item in bindings:
            destination_id = int(item["destination_id"])
            if destination_id in desired:
                raise ValueError("A destination can only be selected once")
            destination = get_destination(db, app_id=app_id, destination_id=destination_id)
            if not destination.enabled or not destination.webhook_url:
                raise ValueError(f"Destination '{destination.name}' is not ready")
            desired[destination_id] = item

        existing = ScheduledTaskOutputBindingRepository.list_by_task(db, task.id)
        by_destination = {binding.destination_id: binding for binding in existing}
        for destination_id, binding in by_destination.items():
            binding.enabled = destination_id in desired
        for destination_id, item in desired.items():
            binding = by_destination.get(destination_id)
            if binding is None:
                binding = ScheduledTaskOutputBinding(scheduled_task_id=task.id, destination_id=destination_id)
                ScheduledTaskOutputBindingRepository.add(db, binding)
            binding.enabled = bool(item.get("enabled", True))
            binding.event_types = ["succeeded"]
        db.commit() if commit else db.flush()
    except ValueError:
        # The caller owns the transaction when commit=False and rolls back itself.
        if commit:
            db.rollback()
        raise
    return task_bindings(db, task=task, app_id=app_id)


def _binding_includes_attachments(destination: OutputDestination) -> bool:
    provider = connector_registry.find_output_provider(destination.provider_key)
    return bool(provider and provider.includes_attachments(destination.public_config))


def task_bindings(db: Session, *, task: ScheduledTask, app_id: int) -> list[dict[str, Any]]:
    return [
        {"destination_id": binding.destination_id, "enabled": binding.enabled,
         "destination_name": binding.destination.name,
         "provider_key": binding.destination.provider_key,
         "include_attachments": _binding_includes_attachments(binding.destination)}
        for binding in ScheduledTaskOutputBindingRepository.list_enabled_view(db, task.id, app_id)
    ]
