"""Plain-dict views of destinations and deliveries for the API layer."""

from typing import Any

from connectors import registry as connector_registry
from connectors.core.settings import read_credentials
from models.output_delivery import OutputDelivery, OutputDestination


def destination_dto(destination: OutputDestination) -> dict[str, Any]:
    return {
        "id": destination.id,
        "app_id": destination.app_id,
        "name": destination.name,
        "provider_key": destination.provider_key,
        "content_mode": destination.content_mode,
        "enabled": destination.enabled,
        "has_secret": bool(destination.webhook_url),
        "public_config": destination.public_config or {},
        "has_credentials": bool(read_credentials(destination.credentials)),
        "created_at": destination.created_at,
        "updated_at": destination.updated_at,
    }


def delivery_dto(delivery: OutputDelivery) -> dict[str, Any]:
    return {
        "id": delivery.id,
        "destination_name": (delivery.destination_snapshot or {}).get("name", "Output destination"),
        "provider_key": (delivery.destination_snapshot or {}).get("provider_key", connector_registry.LEGACY_DEFAULT_PROVIDER_KEY),
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
