"""Explicit allowlisted provider registry (the only module that imports concrete providers)."""

from collections.abc import Mapping
from typing import Annotated

from pydantic import ConfigDict, Field, TypeAdapter

from connectors.core.contracts import Direction, OutboundProvider
from connectors.core.messages import JsonValue
from connectors.core.registry import ProviderRegistry
from connectors.core.settings import DestinationSettingsBase
from connectors.providers.teams_workflow import TeamsWorkflowProvider
from connectors.providers.teams_workflow.config import TeamsWorkflowSettings
from connectors.providers.webhook import WebhookProvider
from connectors.providers.webhook.config import WebhookSettings

DestinationSettings = Annotated[WebhookSettings | TeamsWorkflowSettings, Field(discriminator="provider_key")]
# hide_input_in_errors is honoured only on the root validator: parse untrusted dicts through this adapter,
# not a bare TypeAdapter(DestinationSettings), so ValidationError text never echoes secrets.
DESTINATION_SETTINGS_ADAPTER: TypeAdapter[DestinationSettingsBase] = TypeAdapter(
    DestinationSettings, config=ConfigDict(hide_input_in_errors=True),
)

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


def parse_destination_settings(
    provider_key: str, public_config: Mapping[str, JsonValue] | None, credentials: Mapping[str, str] | None,
) -> DestinationSettingsBase:
    """Parse typed settings through the provider (raises ``ValueError`` with the historical texts)."""
    return get_output_provider(provider_key).parse_settings(public_config, credentials)
