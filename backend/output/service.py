"""Persistence and dispatch helpers for scheduled-task output providers."""

import os
import re
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.output_delivery import OutputDelivery, OutputDeliveryAttempt, OutputDestination, ScheduledTaskOutputBinding
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from output.registry import get_output_provider
from output.teams_workflow import DeliveryError, build_adaptive_card

MAX_ATTEMPTS = 5
LEASE_SECONDS = 120


def _delivery_expiry() -> datetime:
    # Keep pending deliveries inside the file cleanup worker's persistent-file
    # retention window so a card cannot be retried after its links have expired.
    persistent_ttl_days = max(1, int(os.getenv("TMP_PERSISTENT_TTL_DAYS", "7")))
    persistent_ttl_seconds = persistent_ttl_days * 86400
    return datetime.utcnow() + timedelta(seconds=min(30 * 86400, persistent_ttl_seconds - 3600))


def _base_url() -> str:
    return (os.getenv("FRONTEND_URL") or os.getenv("AICT_BASE_URL") or "http://localhost:5173").rstrip("/")


def destination_dto(destination: OutputDestination) -> dict[str, Any]:
    return {
        "id": destination.id,
        "app_id": destination.app_id,
        "name": destination.name,
        "provider_key": destination.provider_key,
        "enabled": destination.enabled,
        "has_secret": bool(destination.webhook_url),
        "created_at": destination.created_at,
        "updated_at": destination.updated_at,
    }


def create_destination(db: Session, *, app_id: int, created_by: int, name: str, webhook_url: str, provider_key: str = "teams_workflow") -> OutputDestination:
    name = name.strip()
    if not name:
        raise ValueError("Destination name is required")
    if len(name) > 255:
        raise ValueError("Destination name is too long")
    provider = get_output_provider(provider_key)
    webhook_url = provider.validate_secret(webhook_url)
    destination = OutputDestination(
        app_id=app_id, created_by=created_by, name=name,
        provider_key=provider_key, public_config={}, webhook_url=webhook_url,
    )
    db.add(destination)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A destination with this name already exists in the app") from exc
    db.refresh(destination)
    return destination


def update_destination(db: Session, destination: OutputDestination, changes: dict[str, Any]) -> OutputDestination:
    if "name" in changes and changes["name"] is not None:
        name = changes["name"].strip()
        if not name or len(name) > 255:
            raise ValueError("Destination name is required and must be at most 255 characters")
        destination.name = name
    if "enabled" in changes and changes["enabled"] is not None:
        destination.enabled = changes["enabled"]
    if changes.get("webhook_url"):
        rotated_url = get_output_provider(destination.provider_key).validate_secret(changes["webhook_url"])
        current_endpoint = urlparse(destination.webhook_url)
        rotated_endpoint = urlparse(rotated_url)
        if (current_endpoint.scheme, current_endpoint.netloc, current_endpoint.path) != (
            rotated_endpoint.scheme, rotated_endpoint.netloc, rotated_endpoint.path,
        ):
            raise ValueError("Changing the Workflow or channel requires creating a new destination")
        destination.webhook_url = rotated_url
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A destination with this name already exists in the app") from exc
    db.refresh(destination)
    return destination


def get_destination(db: Session, *, app_id: int, destination_id: int) -> OutputDestination:
    destination = db.query(OutputDestination).filter(
        OutputDestination.id == destination_id, OutputDestination.app_id == app_id,
    ).one_or_none()
    if destination is None:
        raise ValueError("Output destination not found")
    return destination


def replace_task_bindings(
    db: Session, *, task: ScheduledTask, app_id: int, bindings: list[dict[str, Any]], commit: bool = True,
) -> list[dict[str, Any]]:
    desired: dict[int, dict[str, Any]] = {}
    for item in bindings:
        destination_id = int(item["destination_id"])
        if destination_id in desired:
            raise ValueError("A destination can only be selected once")
        destination = get_destination(db, app_id=app_id, destination_id=destination_id)
        if not destination.enabled or not destination.webhook_url:
            raise ValueError(f"Destination '{destination.name}' is not ready")
        desired[destination_id] = item

    existing = db.query(ScheduledTaskOutputBinding).filter_by(scheduled_task_id=task.id).all()
    by_destination = {binding.destination_id: binding for binding in existing}
    for destination_id, binding in by_destination.items():
        binding.enabled = destination_id in desired
    for destination_id, item in desired.items():
        binding = by_destination.get(destination_id)
        if binding is None:
            binding = ScheduledTaskOutputBinding(scheduled_task_id=task.id, destination_id=destination_id)
            db.add(binding)
        binding.enabled = bool(item.get("enabled", True))
        binding.event_types = ["succeeded"]
        content_mode = item.get("content_mode", "result")
        if content_mode not in {"result", "excerpt", "link_only"}:
            raise ValueError("Unsupported output content mode")
        binding.content_mode = content_mode
    db.commit() if commit else db.flush()
    return task_bindings(db, task=task, app_id=app_id)


def task_bindings(db: Session, *, task: ScheduledTask, app_id: int) -> list[dict[str, Any]]:
    return [
        {"destination_id": binding.destination_id, "enabled": binding.enabled,
         "content_mode": binding.content_mode, "destination_name": binding.destination.name}
        for binding in db.query(ScheduledTaskOutputBinding).join(OutputDestination)
        .filter(ScheduledTaskOutputBinding.scheduled_task_id == task.id,
                OutputDestination.app_id == app_id, ScheduledTaskOutputBinding.enabled.is_(True))
        .order_by(OutputDestination.name).all()
    ]


def _run_payload(task: ScheduledTask, run: ScheduledTaskRun, binding: ScheduledTaskOutputBinding) -> dict[str, Any]:
    base = _base_url()
    result_url = f"{base}/apps/{task.app_id}/scheduled-tasks/{task.id}/runs/{run.id}"
    file_items = []
    for item in run.output_files or []:
        file_id = item.get("file_id")
        if not file_id:
            continue
        file_url = f"{base}/apps/{task.app_id}/scheduled-tasks/{task.id}/runs/{run.id}/files/{quote(str(file_id), safe='')}"
        file_items.append({"filename": str(item.get("filename") or "Output file"), "url": file_url})
    scheduled_time = run.scheduled_time
    if scheduled_time.tzinfo is None:
        scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
    else:
        scheduled_time = scheduled_time.astimezone(timezone.utc)
    result_text = run.output_text or ""
    for item in run.output_files or []:
        file_id = str(item.get("file_id") or "")
        filename = str(item.get("filename") or "output file")
        for identifier in (file_id, filename):
            if identifier:
                result_text = result_text.replace(f"file://{identifier}", filename)
    # Never place local sandbox/file references in a message. The card links below
    # point to the authenticated Mattin AI file route instead.
    result_text = re.sub(r"file://[^\s\])}]+", "[output file]", result_text)
    return build_adaptive_card(
        title=task.name,
        status=run.status,
        scheduled_time=scheduled_time.isoformat(),
        result=result_text,
        view_url=result_url,
        files=file_items,
        content_mode=binding.content_mode,
    )


def create_deliveries_for_run(db: Session, *, task: ScheduledTask, run: ScheduledTaskRun) -> list[OutputDelivery]:
    """Create immutable outbox rows in the caller's run-finalization transaction."""
    bindings = db.query(ScheduledTaskOutputBinding).join(OutputDestination).filter(
        ScheduledTaskOutputBinding.scheduled_task_id == task.id,
        ScheduledTaskOutputBinding.enabled.is_(True),
        OutputDestination.enabled.is_(True),
        OutputDestination.app_id == task.app_id,
    ).all()
    deliveries = []
    for binding in bindings:
        existing = db.query(OutputDelivery).filter_by(
            run_id=run.id, binding_id=binding.id, event_type="succeeded",
        ).one_or_none()
        if existing:
            deliveries.append(existing)
            continue
        destination = binding.destination
        delivery = OutputDelivery(
            run_id=run.id,
            binding_id=binding.id,
            destination_id=destination.id,
            event_type="succeeded",
            destination_snapshot={"provider_key": destination.provider_key, "name": destination.name},
            payload=_run_payload(task, run, binding),
            status="pending",
            expires_at=_delivery_expiry(),
        )
        db.add(delivery)
        deliveries.append(delivery)
    db.flush()
    return deliveries


def delivery_dto(delivery: OutputDelivery) -> dict[str, Any]:
    return {
        "id": delivery.id,
        "destination_name": (delivery.destination_snapshot or {}).get("name", "Output destination"),
        "provider_key": (delivery.destination_snapshot or {}).get("provider_key", "teams_workflow"),
        "event_type": delivery.event_type,
        "status": delivery.status,
        "attempt_count": delivery.attempt_count,
        "next_attempt_at": delivery.next_attempt_at,
        "receipt": delivery.receipt,
        "error_summary": delivery.error_summary,
        "created_at": delivery.created_at,
        "attempts": [{
            "attempt_number": attempt.attempt_number,
            "status": attempt.status,
            "started_at": attempt.started_at,
            "finished_at": attempt.finished_at,
            "http_status": attempt.http_status,
            "error_summary": attempt.error_summary,
        } for attempt in delivery.attempts],
    }


async def test_destination(destination: OutputDestination) -> dict[str, Any]:
    payload = build_adaptive_card(
        title=f"{destination.name}: connection test", status="test", scheduled_time=datetime.now(timezone.utc).isoformat(),
        result="This is a test notification from Mattin AI.", view_url=_base_url(), content_mode="result",
    )
    return await get_output_provider(destination.provider_key).send(destination.webhook_url, payload)


def request_retry(db: Session, delivery: OutputDelivery) -> None:
    if delivery.status not in {"failed", "unknown"}:
        raise ValueError("Only failed or uncertain deliveries can be retried manually")
    if delivery.expires_at and delivery.expires_at <= datetime.utcnow():
        raise ValueError("This delivery expired and can no longer be retried")
    delivery.dispatch_generation += 1
    delivery.status = "pending"
    delivery.next_attempt_at = None
    delivery.lease_until = None
    delivery.error_summary = None
    db.commit()


def _retry_delay(attempt: int) -> float:
    return min(3600.0, 30.0 * (2 ** max(0, attempt - 1))) * random.uniform(0.75, 1.25)


async def process_delivery(delivery_id: int, generation: int) -> None:
    """One guarded POST attempt. A recovered in-flight attempt becomes unknown, never reposted."""
    db = None
    try:
        from db.database import SessionLocal
        db = SessionLocal()
        delivery = db.query(OutputDelivery).filter(OutputDelivery.id == delivery_id).with_for_update().one_or_none()
        if delivery is None or delivery.dispatch_generation != generation:
            return
        now = datetime.utcnow()
        if delivery.status == "sending":
            if delivery.lease_until and delivery.lease_until > now:
                return
            delivery.status = "unknown"
            delivery.error_summary = "Worker stopped while the Teams request was in flight; verify the channel before resending."
            delivery.lease_until = None
            if delivery.attempts:
                delivery.attempts[-1].status = "unknown"
                delivery.attempts[-1].finished_at = now
                delivery.attempts[-1].error_summary = delivery.error_summary
            db.commit()
            return
        if delivery.status != "pending":
            return
        if delivery.expires_at and delivery.expires_at <= now:
            delivery.status = "failed"
            delivery.error_summary = "Delivery expired before it was sent."
            db.commit()
            return
        if not delivery.destination or not delivery.destination.enabled:
            delivery.status = "failed"
            delivery.error_summary = "Output destination is missing or disabled."
            db.commit()
            return
        webhook_url = delivery.destination.webhook_url
        provider_key = (delivery.destination_snapshot or {}).get("provider_key", delivery.destination.provider_key)
        payload = delivery.payload
        delivery.attempt_count += 1
        attempt = OutputDeliveryAttempt(delivery_id=delivery.id, attempt_number=delivery.attempt_count, status="sending")
        db.add(attempt)
        delivery.status = "sending"
        delivery.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        delivery.error_summary = None
        db.commit()
        attempt_id = attempt.id
        db.close()
        db = None

        try:
            receipt = await get_output_provider(provider_key).send(webhook_url, payload)
            outcome = ("accepted", receipt, None, None, None)
        except DeliveryError as exc:
            outcome = (exc.kind, None, exc.http_status, str(exc), exc.retry_after)

        db = SessionLocal()
        delivery = db.query(OutputDelivery).filter_by(id=delivery_id).with_for_update().one_or_none()
        attempt = db.query(OutputDeliveryAttempt).filter_by(id=attempt_id).one_or_none()
        if delivery is None or attempt is None:
            return
        # A late response must not overwrite a retried generation or a lease
        # that the reconciler has already classified as uncertain.
        if delivery.dispatch_generation != generation or delivery.status != "sending" or attempt.status != "sending":
            return
        kind, receipt, http_status, message, retry_after = outcome
        now = datetime.utcnow()
        attempt.finished_at = now
        attempt.http_status = http_status or (receipt or {}).get("http_status")
        delivery.lease_until = None
        if kind == "accepted":
            attempt.status = "accepted"
            delivery.status = "accepted"
            delivery.receipt = receipt
        elif kind == "unknown":
            attempt.status = delivery.status = "unknown"
            attempt.error_summary = delivery.error_summary = message
        elif kind == "retryable" and delivery.attempt_count < MAX_ATTEMPTS:
            attempt.status = "retry_wait"
            delivery.status = "retry_wait"
            delay = retry_after if retry_after is not None else _retry_delay(delivery.attempt_count)
            delivery.next_attempt_at = now + timedelta(seconds=min(max(delay, 1), 86400))
            attempt.error_summary = delivery.error_summary = message
        else:
            attempt.status = "failed"
            delivery.status = "failed"
            attempt.error_summary = delivery.error_summary = message
        db.commit()
    except Exception:
        if db:
            db.rollback()
        raise
    finally:
        if db:
            db.close()
