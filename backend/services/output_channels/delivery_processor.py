"""Guarded delivery attempts and manual retries."""

import asyncio
from datetime import timedelta

from connectors import registry as connector_registry
from connectors.core.errors import DeliveryError
from connectors.core.messages import OutboundRequest
from models.output_delivery import OutputDelivery, OutputDeliveryAttempt
from services.output_channels import delivery_policy, spool
from sqlalchemy.orm import Session
from utils.clock import utcnow_naive


def request_retry(db: Session, delivery: OutputDelivery) -> None:
    if delivery.status not in {"failed", "unknown"}:
        raise ValueError("Only failed or uncertain deliveries can be retried manually")
    if delivery.expires_at and delivery.expires_at <= utcnow_naive():
        raise ValueError("This delivery expired and can no longer be retried")
    delivery.dispatch_generation += 1
    delivery.status = "pending"
    delivery.next_attempt_at = None
    delivery.lease_until = None
    delivery.error_summary = None
    db.commit()


async def process_delivery(delivery_id: int, generation: int) -> None:
    """One guarded POST attempt. A recovered in-flight attempt becomes unknown, never reposted."""
    db = None
    try:
        from db.database import SessionLocal
        db = SessionLocal()
        delivery = db.query(OutputDelivery).filter(OutputDelivery.id == delivery_id).with_for_update().one_or_none()
        if delivery is None or delivery.dispatch_generation != generation:
            return
        now = utcnow_naive()
        if delivery.status == "sending":
            if delivery.lease_until and delivery.lease_until > now:
                return
            snapshot = delivery.destination_snapshot or {}
            retry_deduplicated = (
                delivery_policy.receiver_can_deduplicate(snapshot.get("provider_key"), snapshot)
                and delivery.attempt_count < delivery_policy.MAX_ATTEMPTS
                and (not delivery.expires_at or delivery.expires_at > now)
            )
            delivery.status = "retry_wait" if retry_deduplicated else "unknown"
            delivery.error_summary = (
                "Webhook worker stopped during an idempotent request; retry scheduled."
                if retry_deduplicated else
                "Worker stopped while the external request was in flight; verify receipt before resending."
            )
            if retry_deduplicated:
                delivery.next_attempt_at = now + timedelta(seconds=30)
            delivery.lease_until = None
            if delivery.attempts:
                delivery.attempts[-1].status = delivery.status
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
        snapshot = dict(delivery.destination_snapshot or {})
        credentials = dict(delivery.destination.credentials or {})
        request_body = delivery.request_body
        request_body_key = delivery.request_body_path
        request_body_size = delivery.request_body_size
        request_body_sha256 = delivery.request_body_sha256
        delivery.attempt_count += 1
        attempt_number = delivery.attempt_count
        attempt = OutputDeliveryAttempt(delivery_id=delivery.id, attempt_number=delivery.attempt_count, status="sending")
        db.add(attempt)
        delivery.status = "sending"
        snapshot = delivery.destination_snapshot or {}
        lease_seconds = delivery_policy.lease_seconds_for(snapshot)
        delivery.lease_until = now + timedelta(seconds=lease_seconds)
        delivery.error_summary = None
        db.commit()
        attempt_id = attempt.id
        db.close()
        db = None

        try:
            async with asyncio.timeout(lease_seconds - delivery_policy.SEND_DEADLINE_MARGIN_SECONDS):
                body = request_body
                body_path = None
                if request_body_key:
                    path = spool.safe_spool_file(request_body_key)
                    if not path.is_file() or path.stat().st_size != request_body_size:
                        raise DeliveryError("Prepared webhook request body is missing or incomplete", kind="permanent")
                    if await asyncio.to_thread(spool.file_sha256, path) != request_body_sha256:
                        raise DeliveryError("Prepared webhook request body failed integrity validation", kind="permanent")
                    body_path = str(path)
                    body = None
                provider = connector_registry.get_output_provider(provider_key)
                receipt = await provider.send(OutboundRequest(
                    url=webhook_url, payload=payload, public_config=provider.snapshot_public_config(snapshot),
                    credentials=credentials, event_id=payload.get("event_id"), attempt_number=attempt_number,
                    content_type=snapshot.get("content_type", "application/json"),
                    body=body, body_path=body_path,
                ))
            outcome = ("accepted", receipt, None, None, None)
        except DeliveryError as exc:
            outcome = (exc.kind, None, exc.http_status, str(exc), exc.retry_after)
        except TimeoutError:
            # Bytes may already have reached the receiver: only a destination whose
            # receiver deduplicates can safely be retried.
            deduplicates = delivery_policy.receiver_can_deduplicate(provider_key, snapshot)
            outcome = (
                "retryable" if deduplicates else "unknown", None, None,
                "Delivery did not finish within its lease; acceptance may be unknown", None,
            )

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
        now = utcnow_naive()
        attempt.finished_at = now
        attempt.http_status = http_status or (receipt or {}).get("http_status")
        delivery.lease_until = None
        if kind == "accepted":
            attempt.status = "accepted"
            delivery.status = "accepted"
            delivery.receipt = receipt
            # Never sent again: the spool file goes with the next cleanup sweep.
            delivery.request_body = None
            delivery.request_body_path = None
        elif kind == "unknown":
            attempt.status = delivery.status = "unknown"
            attempt.error_summary = delivery.error_summary = message
        elif kind == "retryable" and delivery.attempt_count < delivery_policy.MAX_ATTEMPTS:
            attempt.status = "retry_wait"
            delivery.status = "retry_wait"
            delay = retry_after if retry_after is not None else delivery_policy.retry_delay(delivery.attempt_count)
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
