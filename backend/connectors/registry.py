"""Explicit allowlisted provider registry (the only module that imports concrete providers)."""

from connectors.core.contracts import Direction, OutboundProvider
from connectors.core.registry import ProviderRegistry
from connectors.providers.teams_workflow import TeamsWorkflowProvider
from connectors.providers.webhook import WebhookProvider

# Provider assumed for stored rows that predate the ``provider_key`` column semantics.
LEGACY_DEFAULT_PROVIDER_KEY = "teams_workflow"

_REGISTRY = ProviderRegistry({
    "teams_workflow": TeamsWorkflowProvider(),
    "webhook": WebhookProvider(),
})


def get_output_provider(provider_key: str) -> OutboundProvider:
    """Return the outbound provider or raise ``ProviderNotFoundError`` (a ``ValueError``)."""
    return _REGISTRY.get_outbound(provider_key)


def find_output_provider(provider_key: str | None) -> OutboundProvider | None:
    return _REGISTRY.find_outbound(provider_key)


def list_output_providers() -> list[OutboundProvider]:
    return _REGISTRY.list_outbound()


def list_providers(direction: Direction | None = None) -> list[object]:
    return _REGISTRY.list(direction)


def registered_keys() -> frozenset[str]:
    return _REGISTRY.keys()


def spool_attachment_provider_keys() -> tuple[str, ...]:
    return _REGISTRY.outbound_keys_where(lambda capabilities: capabilities.spooled_attachments)
