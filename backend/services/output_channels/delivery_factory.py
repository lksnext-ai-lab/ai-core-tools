"""Creation of the immutable delivery outbox rows for a finished run."""

from typing import Any

from connectors import registry as connector_registry
from connectors.core.messages import BodyEncoding, RunDeliveryContext
from models.output_delivery import OutputArtifact, OutputDelivery
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from repositories.output_artifact_repository import OutputArtifactRepository
from repositories.output_delivery_repository import OutputDeliveryRepository
from repositories.scheduled_task_output_binding_repository import (
    ScheduledTaskOutputBindingRepository,
)
from services.output_channels import delivery_policy, messages, spool
from sqlalchemy.orm import Session


def create_deliveries_for_run(
    db: Session, *, task: ScheduledTask, run: ScheduledTaskRun,
    artifacts: list[dict[str, Any]] | None = None, attachment_error: str | None = None,
) -> list[OutputDelivery]:
    """Create immutable outbox rows in the caller's run-finalization transaction."""
    bindings = ScheduledTaskOutputBindingRepository.list_enabled_with_enabled_destination(db, task.id, task.app_id)
    deliveries = []
    # One artifact row per run file, shared by every attachment destination.
    # Tracked in memory: with autoflush off, rows added for an earlier binding
    # are not visible to a query yet.
    known_artifacts: set[str] | None = None
    for binding in bindings:
        existing = OutputDeliveryRepository.find_existing(db, run.id, binding.id, "succeeded")
        if existing:
            deliveries.append(existing)
            continue
        destination = binding.destination
        provider = connector_registry.find_output_provider(destination.provider_key) \
            or connector_registry.get_output_provider(connector_registry.LEGACY_DEFAULT_PROVIDER_KEY)
        view = messages.destination_view(destination)
        snapshot = provider.build_snapshot(view)
        prepared = provider.build_run_delivery(
            RunDeliveryContext(messages.run_message_from(task, run), view, tuple(artifacts or ())),
        )
        payload = prepared.payload
        destination_artifacts = list(prepared.attachments)
        body = None
        request_body_path = None
        request_body_size = None
        request_body_sha256 = None
        content_type = "application/json"
        status = "pending"
        error = attachment_error if prepared.requires_attachments else None
        if error:
            status = "failed"
        elif prepared.body_encoding != BodyEncoding.NONE:
            try:
                body = spool.json_body(payload)
                if prepared.body_encoding == BodyEncoding.MULTIPART:
                    if not prepared.event_id:
                        raise ValueError("multipart deliveries require an event_id")
                    key = f"deliveries/{prepared.event_id.replace('-', '')}.multipart"
                    content_type, request_body_size, request_body_sha256 = spool.write_multipart(
                        spool.safe_spool_file(key), payload, destination_artifacts,
                    )
                    request_body_path = key
            except Exception as exc:
                status = "failed"
                error = str(exc)[:300]
                body = None
        if prepared.body_encoding != BodyEncoding.NONE:
            snapshot["content_type"] = content_type
        delivery = OutputDelivery(
            run_id=run.id,
            binding_id=binding.id,
            destination_id=destination.id,
            event_type="succeeded",
            destination_snapshot=snapshot,
            payload=payload,
            request_body=body,
            request_body_path=request_body_path,
            request_body_size=request_body_size,
            request_body_sha256=request_body_sha256,
            status=status,
            error_summary=error,
            expires_at=delivery_policy.delivery_expiry(),
        )
        OutputDeliveryRepository.add(db, delivery)
        deliveries.append(delivery)
        if prepared.requires_attachments and not attachment_error:
            if known_artifacts is None:
                known_artifacts = OutputArtifactRepository.file_ids_for_run(db, run.id)
            for artifact in destination_artifacts:
                if artifact["file_id"] not in known_artifacts:
                    known_artifacts.add(artifact["file_id"])
                    OutputArtifactRepository.add(db, OutputArtifact(
                        run_id=run.id,
                        file_id=artifact["file_id"], filename=artifact["filename"],
                        content_type=artifact["content_type"], size_bytes=artifact["size_bytes"],
                        sha256=artifact["sha256"], object_key=artifact["object_key"],
                    ))
    db.flush()
    return deliveries
