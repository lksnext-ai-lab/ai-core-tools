"""Delivery policy shared by the processor and the DBOS reconciler (capability driven)."""

import os
import random
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from connectors import registry as connector_registry
from connectors.core.messages import JsonValue
from models.output_delivery import OutputDelivery
from utils.clock import utcnow_naive

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


STALE_RETRY_SUMMARY = "Webhook worker stopped during an idempotent request; retry scheduled."
STALE_UNKNOWN_SUMMARY = "Worker stopped while the external request was in flight; verify receipt before resending."
STALE_RETRY_DELAY_SECONDS = 30


@dataclass(frozen=True)
class StaleSendingOutcome:
    """Result of classifying a ``sending`` delivery whose lease expired."""

    status: Literal["retry_wait", "unknown"]
    error_summary: str
    next_attempt_at: datetime | None


def classify_stale_sending(
    snapshot: Mapping[str, JsonValue] | None,
    *,
    attempt_count: int,
    expires_at: datetime | None,
    now: datetime,
) -> StaleSendingOutcome:
    """Single rule for an abandoned in-flight send.

    Retry only when the receiver deduplicates, attempts remain and the delivery has not expired;
    otherwise the outcome is uncertain and must be verified by a human. Unknown providers are `unknown`.
    """
    data: Mapping[str, JsonValue] = snapshot if isinstance(snapshot, Mapping) else {}
    key = data.get("provider_key")
    retry = (
        receiver_can_deduplicate(key if isinstance(key, str) else None, data)
        and attempt_count < MAX_ATTEMPTS
        and (expires_at is None or expires_at > now)
    )
    if retry:
        return StaleSendingOutcome(
            "retry_wait", STALE_RETRY_SUMMARY, now + timedelta(seconds=STALE_RETRY_DELAY_SECONDS),
        )
    return StaleSendingOutcome("unknown", STALE_UNKNOWN_SUMMARY, None)


def apply_stale_sending(delivery: OutputDelivery, now: datetime) -> None:
    """Classify an expired ``sending`` delivery and record the outcome on it and its last attempt."""
    outcome = classify_stale_sending(
        delivery.destination_snapshot,
        attempt_count=delivery.attempt_count, expires_at=delivery.expires_at, now=now,
    )
    delivery.status = outcome.status
    delivery.error_summary = outcome.error_summary
    if outcome.next_attempt_at is not None:
        delivery.next_attempt_at = outcome.next_attempt_at
    delivery.lease_until = None
    if delivery.attempts:
        attempt = delivery.attempts[-1]
        attempt.status = outcome.status
        attempt.finished_at = now
        attempt.error_summary = outcome.error_summary


def lease_seconds_for(snapshot: Mapping[str, JsonValue]) -> int:
    """Lease duration for one attempt; destinations with attachments get the provider's extended lease."""
    key = snapshot.get("provider_key")
    provider = connector_registry.find_output_provider(key if isinstance(key, str) else None)
    capabilities = provider.descriptor.outbound if provider else None
    if (provider and capabilities and capabilities.attachment_lease_seconds
            and provider.includes_attachments(provider.snapshot_public_config(snapshot))):
        return capabilities.attachment_lease_seconds
    return LEASE_SECONDS


def delivery_expiry() -> datetime:
    # Keep pending deliveries inside the file cleanup worker's persistent-file
    # retention window so a card cannot be retried after its links have expired.
    persistent_ttl_days = max(1, int(os.getenv("TMP_PERSISTENT_TTL_DAYS", "7")))
    persistent_ttl_seconds = persistent_ttl_days * 86400
    return utcnow_naive() + timedelta(seconds=min(30 * 86400, persistent_ttl_seconds - 3600))


def retry_delay(attempt: int) -> float:
    return min(3600.0, 30.0 * (2 ** max(0, attempt - 1))) * random.uniform(0.75, 1.25)
