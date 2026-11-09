"""Generic, signed JSON/multipart webhook output provider."""

import asyncio
import base64
import hashlib
import hmac
import os
import time
import uuid
from collections.abc import Mapping
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import httpx
from utils.ssrf_guard import (
    FetchUnresolvableError,
    SsrfBlockedError,
)

from connectors.core.contracts import (
    OutboundCapabilities,
    ProviderDescriptor,
    UpdatePolicy,
)
from connectors.core.errors import DeliveryError, DeliveryErrorKind
from connectors.core.http import ensure_public_host, parse_retry_after, pinned_client
from connectors.core.messages import (
    AttachmentStager,
    BodyEncoding,
    DestinationExample,
    DestinationView,
    JsonDict,
    JsonValue,
    OutboundRequest,
    PreparedDelivery,
    RunDeliveryContext,
    SendReceipt,
    TestDeliveryContext,
    ValidatedDestination,
)
from connectors.providers.webhook.events import (
    attachment_manifest,
    build_run_event,
    build_test_event,
)

_PUBLIC_CONFIG_KEYS = frozenset({"schema_version", "auth_mode", "receiver_deduplicates", "include_attachments"})


def check_webhook_url(value: str) -> str:
    """Structural checks only (no DNS): HTTPS on port 443, no user info or fragment."""
    raw = (value or "").strip()
    parsed = urlparse(raw)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Webhook URL must be an HTTPS URL without user info or a fragment")
    if parsed.port not in (None, 443):
        raise ValueError("Webhook URL must use port 443")
    return raw


def validate_webhook_url(value: str) -> str:
    """Structural checks plus a public DNS target.

    Resolves DNS synchronously: call it from sync code only. Sends re-check the
    resolved address through the pinned transport instead.
    """
    raw = check_webhook_url(value)
    ensure_public_host(urlparse(raw).hostname.lower().rstrip("."), "Webhook")
    return raw


def validate_webhook_config(config: dict[str, Any] | None, credentials: dict[str, str] | None) -> dict[str, Any]:
    config = dict(config or {})
    credentials = dict(credentials or {})
    if set(config) - _PUBLIC_CONFIG_KEYS:
        raise ValueError("Webhook configuration contains unsupported fields")
    if config.get("schema_version", "1") != "1":
        raise ValueError("Unsupported webhook schema version")
    config["schema_version"] = "1"
    auth_mode = config.get("auth_mode", "hmac_sha256")
    if auth_mode not in {"hmac_sha256", "bearer", "none"}:
        raise ValueError("Unsupported webhook authentication mode")
    config["auth_mode"] = auth_mode
    config["receiver_deduplicates"] = config.get("receiver_deduplicates", False)
    config["include_attachments"] = config.get("include_attachments", False)
    if type(config["receiver_deduplicates"]) is not bool or type(config["include_attachments"]) is not bool:
        raise ValueError("Webhook boolean configuration values must be true or false")
    if auth_mode == "hmac_sha256":
        encoded = credentials.get("signing_secret", "")
        try:
            key = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("HMAC signing secret must be base64 encoded") from exc
        if len(key) != 32 or set(credentials) != {"signing_secret"}:
            raise ValueError("HMAC signing secret must contain exactly 32 random bytes")
    elif auth_mode == "bearer":
        token = credentials.get("bearer_token", "")
        if not token or len(token) > 4096 or any(ord(char) < 33 or ord(char) > 126 for char in token):
            raise ValueError("Bearer token must be a non-empty printable ASCII token")
        if set(credentials) != {"bearer_token"}:
            raise ValueError("Bearer authentication accepts only a bearer token")
    elif credentials:
        raise ValueError("Authentication mode none does not accept credentials")
    return config


async def _file_stream(path: str) -> AsyncIterator[bytes]:
    source = await asyncio.to_thread(open, path, "rb")
    try:
        while True:
            chunk = await asyncio.to_thread(source.read, 64 * 1024)
            if not chunk:
                break
            yield chunk
    finally:
        await asyncio.to_thread(source.close)


def _signature(key: bytes, event_id: str, timestamp: str, content_type: str, body: bytes | None, path: str | None) -> str:
    signer = hmac.new(key, f"{event_id}.{timestamp}.{content_type}.".encode("ascii"), hashlib.sha256)
    if body is not None:
        signer.update(body)
    elif path:
        with open(path, "rb") as source:
            for chunk in iter(lambda: source.read(256 * 1024), b""):
                signer.update(chunk)
    return signer.hexdigest()


async def _send_webhook(
    secret: str,
    payload: dict[str, Any],
    *,
    config: dict[str, Any],
    credentials: dict[str, str],
    event_id: str,
    attempt_number: int,
    content_type: str,
    body: bytes | None = None,
    body_path: str | None = None,
) -> SendReceipt:
    try:
        check_webhook_url(secret)
        validated = validate_webhook_config(config, credentials)
    except ValueError as exc:
        raise DeliveryError(str(exc), kind="permanent") from exc
    if body is None and body_path is None:
        raise DeliveryError("Prepared webhook request body is missing", kind="permanent")
    try:
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": content_type,
            "X-Mattin-Event-Id": event_id,
            "X-Mattin-Event-Type": str(payload.get("event_type", "task.run.succeeded")),
            "X-Mattin-Attempt": str(attempt_number),
            "Idempotency-Key": event_id,
        }
        if body is not None:
            headers["Content-Length"] = str(len(body))
        elif body_path:
            headers["Content-Length"] = str(os.path.getsize(body_path))
        if validated["auth_mode"] == "bearer":
            headers["Authorization"] = f"Bearer {credentials['bearer_token']}"
        elif validated["auth_mode"] == "hmac_sha256":
            key = base64.b64decode(credentials["signing_secret"], validate=True)
            headers["X-Mattin-Timestamp"] = timestamp
            signature = await asyncio.to_thread(_signature, key, event_id, timestamp, content_type, body, body_path)
            headers["X-Mattin-Signature"] = "v1=" + signature
        content: bytes | AsyncIterator[bytes] = body if body is not None else _file_stream(body_path or "")
        timeout = 120.0 if content_type.startswith("multipart/form-data") else 20.0
        async with pinned_client(timeout) as client:
            async with client.stream("POST", secret, headers=headers, content=content) as response:
                status_code = response.status_code
                retry_after_value = response.headers.get("Retry-After")
    except FetchUnresolvableError as exc:
        raise DeliveryError("Webhook host could not be resolved", kind="retryable") from exc
    except SsrfBlockedError as exc:
        raise DeliveryError("Webhook URL cannot target a private or reserved network", kind="permanent") from exc
    except httpx.ConnectTimeout as exc:
        raise DeliveryError("Could not connect to webhook before sending", kind="retryable") from exc
    except httpx.ConnectError as exc:
        raise DeliveryError("Could not connect to webhook before sending", kind="retryable") from exc
    except httpx.TimeoutException as exc:
        kind: DeliveryErrorKind = "retryable" if validated["receiver_deduplicates"] else "unknown"
        raise DeliveryError("Webhook request timed out; acceptance may be unknown", kind=kind) from exc
    except httpx.RequestError as exc:
        kind = "retryable" if validated["receiver_deduplicates"] else "unknown"
        raise DeliveryError("Webhook request failed; acceptance may be unknown", kind=kind) from exc

    if 200 <= status_code < 300:
        return {"http_status": status_code, "event_id": event_id}
    if status_code == 429:
        raise DeliveryError(
            "Webhook rejected the request due to throttling", kind="retryable", http_status=429,
            retry_after=parse_retry_after(retry_after_value),
        )
    if status_code >= 500 or status_code == 408:
        kind = "retryable" if validated["receiver_deduplicates"] else "unknown"
        raise DeliveryError(f"Webhook returned HTTP {status_code}; acceptance may be unknown", kind=kind, http_status=status_code)
    raise DeliveryError(f"Webhook rejected the request (HTTP {status_code})", kind="permanent", http_status=status_code)


class WebhookProvider:
    descriptor = ProviderDescriptor(
        key="webhook",
        name="Webhook",
        supports_links=True,
        supports_native_attachments=False,
        supports_binary_attachments=True,
        outbound=OutboundCapabilities(
            receiver_deduplication=True, spooled_attachments=True, attachment_lease_seconds=180,
            update_policy=UpdatePolicy.REVALIDATE_ALL,
        ),
    )

    def validate_secret(self, value: str) -> str:
        return validate_webhook_url(value)

    def validate_destination(
        self, url: str, public_config: Mapping[str, JsonValue] | None, credentials: Mapping[str, str] | None,
    ) -> ValidatedDestination:
        return ValidatedDestination(
            validate_webhook_url(url),
            validate_webhook_config(dict(public_config) if public_config is not None else None,
                                    dict(credentials) if credentials is not None else None),
            dict(credentials or {}),
        )

    def ensure_same_endpoint(self, current_url: str, new_url: str) -> None:
        current, new = urlparse(current_url), urlparse(new_url)
        if (current.scheme, current.netloc, current.path, current.query) != (new.scheme, new.netloc, new.path, new.query):
            raise ValueError("Changing a webhook endpoint requires creating a new destination")

    def includes_attachments(self, public_config: Mapping[str, JsonValue] | None) -> bool:
        return bool((public_config or {}).get("include_attachments", False))

    def receiver_deduplicates(self, public_config: Mapping[str, JsonValue] | None) -> bool:
        return (public_config or {}).get("receiver_deduplicates") is True

    def build_snapshot(self, destination: DestinationView) -> JsonDict:
        snapshot: JsonDict = {
            "provider_key": destination.provider_key, "name": destination.name,
            "content_mode": destination.content_mode,
        }
        snapshot.update(dict(destination.public_config or {}))
        return snapshot

    def snapshot_public_config(self, snapshot: Mapping[str, JsonValue]) -> JsonDict:
        return {key: value for key, value in snapshot.items() if key in _PUBLIC_CONFIG_KEYS}

    def build_run_delivery(self, context: RunDeliveryContext) -> PreparedDelivery:
        include = self.includes_attachments(context.destination.public_config)
        event_id = str(uuid.uuid4())
        artifacts = tuple(context.artifacts or ()) if include else ()
        payload = build_run_event(
            context.message, content_mode=context.destination.content_mode, event_id=event_id, artifacts=artifacts,
        )
        return PreparedDelivery(
            payload, event_id, BodyEncoding.MULTIPART if include else BodyEncoding.JSON, artifacts,
            requires_attachments=include,
        )

    def build_test_delivery(self, context: TestDeliveryContext, stager: AttachmentStager) -> PreparedDelivery:
        event_id = str(uuid.uuid4())
        payload = build_test_event(
            app_id=context.destination.app_id, content_mode=context.destination.content_mode, event_id=event_id,
            base_url=context.base_url, now=context.now,
        )
        if not self.includes_attachments(context.destination.public_config):
            return PreparedDelivery(payload, event_id, BodyEncoding.JSON)
        artifact = stager.stage(
            f"tests/{event_id}.txt", b"Mattin AI webhook attachment test.\n",
            file_id="destination-test-file", filename="prueba.txt", content_type="text/plain", part_name="file_1",
        )
        payload["attachments"] = list(attachment_manifest([artifact]))
        return PreparedDelivery(payload, event_id, BodyEncoding.MULTIPART, (artifact,))

    async def send(self, request: OutboundRequest) -> SendReceipt:
        return await _send_webhook(
            request.url, request.payload,
            config=dict(request.public_config), credentials=dict(request.credentials),
            event_id=request.event_id, attempt_number=request.attempt_number,
            content_type=request.content_type, body=request.body, body_path=request.body_path,
        )

    def example_destination(self) -> DestinationExample:
        config: JsonDict = {
            "schema_version": "1", "auth_mode": "hmac_sha256",
            "receiver_deduplicates": False, "include_attachments": False,
        }
        return DestinationExample(
            "https://hooks.example.com/mattin", config,
            {"signing_secret": base64.b64encode(b"0" * 32).decode("ascii")},
            {**config, "receiver_deduplicates": True},
        )
