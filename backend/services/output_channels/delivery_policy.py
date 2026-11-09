"""Delivery policy shared by the processor and the DBOS reconciler (capability driven)."""

from collections.abc import Mapping

from connectors import registry as connector_registry
from connectors.core.messages import JsonValue

MAX_ATTEMPTS = 5
# A prepared request body is still needed while a send can happen: automatically
# (pending/retry_wait/sending) or by manual retry (failed/unknown) until expiry.
BODY_NEEDED_STATUSES = ("pending", "retry_wait", "sending", "failed", "unknown")
LEASE_SECONDS = 120
# A send must finish (or give up) this long before its lease expires, so the
# worker always records the outcome before the reconciler treats the attempt
# as abandoned.
SEND_DEADLINE_MARGIN_SECONDS = 15


def receiver_can_deduplicate(provider_key: str | None, snapshot: Mapping[str, JsonValue]) -> bool:
    """True when the provider supports receiver-side deduplication and the destination opted in."""
    provider = connector_registry.find_output_provider(provider_key)
    return bool(
        provider and provider.descriptor.outbound
        and provider.descriptor.outbound.receiver_deduplication
        and provider.receiver_deduplicates(provider.snapshot_public_config(snapshot)),
    )


def lease_seconds_for(snapshot: Mapping[str, JsonValue]) -> int:
    """Lease duration for one attempt; destinations with attachments get the provider's extended lease."""
    key = snapshot.get("provider_key")
    provider = connector_registry.find_output_provider(key if isinstance(key, str) else None)
    capabilities = provider.descriptor.outbound if provider else None
    if (provider and capabilities and capabilities.attachment_lease_seconds
            and provider.includes_attachments(provider.snapshot_public_config(snapshot))):
        return capabilities.attachment_lease_seconds
    return LEASE_SECONDS
