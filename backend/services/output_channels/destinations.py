"""Output destination management (create, update, read) and provider descriptors."""

from dataclasses import dataclass
from typing import Any, assert_never

from connectors import registry as connector_registry
from connectors.core.contracts import OutboundProvider, UpdatePolicy
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


_UNCHANGED: Any = object()  # sentinel: leave the column untouched (None is a real value for credentials)


@dataclass(frozen=True)
class _EndpointPatch:
    """Validated URL/config/credentials values to write; ``_UNCHANGED`` leaves a column alone."""

    url: Any = _UNCHANGED
    public_config: Any = _UNCHANGED
    credentials: Any = _UNCHANGED


def _validate_endpoint_changes(
    provider: OutboundProvider, destination: OutputDestination, changes: dict[str, Any],
) -> _EndpointPatch:
    """Validate URL/config/credentials according to the provider's update policy, without mutating anything."""
    outbound = provider.descriptor.outbound
    assert outbound is not None, "the registry only returns providers that declare outbound capabilities"
    match outbound.update_policy:
        case UpdatePolicy.REVALIDATE_ALL:
            candidate_url = changes.get("webhook_url") or destination.webhook_url
            new_config = (
                changes.get("public_config") if changes.get("public_config") is not None
                else dict(destination.public_config or {})
            )
            new_credentials = dict(destination.credentials or {})
            if changes.get("clear_credentials"):
                new_credentials = {}
            if changes.get("credentials") is not None:
                new_credentials = dict(changes["credentials"])
            validated = provider.validate_destination(candidate_url, new_config, new_credentials)
            if changes.get("webhook_url"):
                provider.ensure_same_endpoint(destination.webhook_url, validated.url)
            return _EndpointPatch(
                url=validated.url, public_config=validated.public_config, credentials=new_credentials or None,
            )
        case UpdatePolicy.ROTATE_URL_ONLY:
            new_url: Any = _UNCHANGED
            if changes.get("webhook_url"):
                validated = provider.validate_destination(changes["webhook_url"], None, None)
                provider.ensure_same_endpoint(destination.webhook_url, validated.url)
                new_url = validated.url
            if changes.get("public_config") is not None or changes.get("credentials") is not None:
                # Providers with this policy take no settings: any non-empty config/credentials is rejected here.
                provider.parse_settings(changes.get("public_config") or {}, changes.get("credentials") or {})
            return _EndpointPatch(url=new_url)
        case unexpected:
            assert_never(unexpected)


def update_destination(db: Session, destination: OutputDestination, changes: dict[str, Any]) -> OutputDestination:
    """Update a destination atomically: validate everything first, then apply and save.

    The validation phase never touches the ORM object, so a rejected request leaves no partial changes.
    """
    # Phase 1: validation (no mutation). Order preserves the historical error precedence.
    new_name: str | None = None
    if "name" in changes and changes["name"] is not None:
        new_name = changes["name"].strip()
        if not new_name or len(new_name) > 255:
            raise ValueError("Destination name is required and must be at most 255 characters")
    provider = connector_registry.get_output_provider(destination.provider_key)
    if changes.get("content_mode") is not None and changes["content_mode"] not in provider.descriptor.content_modes:
        raise ValueError("Unsupported output content mode")
    patch = _validate_endpoint_changes(provider, destination, changes)
    # Phase 2: apply (same field order as before) and save.
    if new_name is not None:
        destination.name = new_name
    if "enabled" in changes and changes["enabled"] is not None:
        destination.enabled = changes["enabled"]
    if changes.get("content_mode") is not None:
        destination.content_mode = changes["content_mode"]
    if patch.public_config is not _UNCHANGED:
        destination.public_config = patch.public_config
    if patch.credentials is not _UNCHANGED:
        destination.credentials = patch.credentials
    if patch.url is not _UNCHANGED:
        destination.webhook_url = patch.url
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
