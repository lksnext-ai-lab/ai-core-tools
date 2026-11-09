"""Output destination management (create, update, read) and provider descriptors."""

from typing import Any

from connectors import registry as connector_registry
from connectors.core.contracts import UpdatePolicy
from models.output_delivery import OutputDestination
from repositories.output_delivery_repository import OutputDeliveryRepository
from repositories.output_destination_repository import OutputDestinationRepository
from services.output_channels.dto import destination_dto
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def list_provider_descriptors() -> list[dict[str, Any]]:
    """Descriptor summary of every registered output provider."""
    return [{"key": provider.descriptor.key, "name": provider.descriptor.name,
             "supports_links": provider.descriptor.supports_links,
             "supports_native_attachments": provider.descriptor.supports_native_attachments,
             "supports_binary_attachments": provider.descriptor.supports_binary_attachments,
             "content_modes": list(provider.descriptor.content_modes)}
            for provider in connector_registry.list_output_providers()]


def create_destination(
    db: Session, *, app_id: int, created_by: int, name: str, webhook_url: str,
    provider_key: str = connector_registry.LEGACY_DEFAULT_PROVIDER_KEY, public_config: dict[str, Any] | None = None,
    credentials: dict[str, str] | None = None,
    content_mode: str = "result",
) -> OutputDestination:
    name = name.strip()
    if not name:
        raise ValueError("Destination name is required")
    if len(name) > 255:
        raise ValueError("Destination name is too long")
    provider = connector_registry.get_output_provider(provider_key)
    if content_mode not in provider.descriptor.content_modes:
        raise ValueError("Unsupported output content mode")
    validated = provider.validate_destination(webhook_url, dict(public_config or {}), credentials)
    destination = OutputDestination(
        app_id=app_id, created_by=created_by, name=name,
        provider_key=provider_key, public_config=validated.public_config, webhook_url=validated.url,
        content_mode=content_mode,
        credentials=credentials,
    )
    try:
        OutputDestinationRepository.create(db, destination)
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A destination with this name already exists in the app") from exc
    return destination


def update_destination(db: Session, destination: OutputDestination, changes: dict[str, Any]) -> OutputDestination:
    if "name" in changes and changes["name"] is not None:
        name = changes["name"].strip()
        if not name or len(name) > 255:
            raise ValueError("Destination name is required and must be at most 255 characters")
        destination.name = name
    if "enabled" in changes and changes["enabled"] is not None:
        destination.enabled = changes["enabled"]
    provider = connector_registry.get_output_provider(destination.provider_key)
    if changes.get("content_mode") is not None:
        if changes["content_mode"] not in provider.descriptor.content_modes:
            raise ValueError("Unsupported output content mode")
        destination.content_mode = changes["content_mode"]
    update_policy = provider.descriptor.outbound.update_policy if provider.descriptor.outbound else None
    if update_policy == UpdatePolicy.REVALIDATE_ALL:
        new_url = changes.get("webhook_url") or destination.webhook_url
        new_config = changes.get("public_config") if changes.get("public_config") is not None else dict(destination.public_config or {})
        new_credentials = dict(destination.credentials or {})
        if changes.get("clear_credentials"):
            new_credentials = {}
        if changes.get("credentials") is not None:
            new_credentials = dict(changes["credentials"])
        validated = provider.validate_destination(new_url, new_config, new_credentials)
        if "webhook_url" in changes and changes["webhook_url"]:
            provider.ensure_same_endpoint(destination.webhook_url, validated.url)
        destination.public_config = validated.public_config
        destination.credentials = new_credentials or None
        destination.webhook_url = validated.url
    elif changes.get("webhook_url"):
        validated = provider.validate_destination(changes["webhook_url"], None, None)
        provider.ensure_same_endpoint(destination.webhook_url, validated.url)
        destination.webhook_url = validated.url
    try:
        OutputDestinationRepository.save(db, destination)
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A destination with this name already exists in the app") from exc
    return destination


def get_destination(db: Session, *, app_id: int, destination_id: int) -> OutputDestination:
    destination = OutputDestinationRepository.get_by_id_and_app_id(db, destination_id, app_id)
    if destination is None:
        raise ValueError("Output destination not found")
    return destination


def list_destinations(db: Session, app_id: int) -> list[dict[str, Any]]:
    """Enabled destinations of an app as dtos, ordered by name."""
    return [destination_dto(item) for item in OutputDestinationRepository.list_enabled_by_app(db, app_id)]


def delete_destination(db: Session, *, app_id: int, destination_id: int) -> None:
    """Delete a destination, or only deactivate it (keeping delivery history) when tasks are bound to it."""
    destination = get_destination(db, app_id=app_id, destination_id=destination_id)
    if destination.bindings:
        # Keep delivery history but remove this destination from every task.
        OutputDestinationRepository.deactivate_with_bindings(db, destination)
        OutputDeliveryRepository.cancel_pending_for_destination(db, destination_id)
    else:
        OutputDestinationRepository.delete(db, destination)
    db.commit()
