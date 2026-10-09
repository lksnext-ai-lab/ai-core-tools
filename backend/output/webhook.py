"""Generic, signed JSON/multipart webhook output provider."""

import asyncio
import base64
import hashlib
import hmac
import os
import time
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import httpx

from output.contracts import ProviderDescriptor
from output.teams_workflow import DeliveryError, ensure_public_host



def validate_webhook_url(value: str) -> str:
    raw = (value or "").strip()
    parsed = urlparse(raw)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Webhook URL must be an HTTPS URL without user info or a fragment")
    if parsed.port not in (None, 443):
        raise ValueError("Webhook URL must use port 443")
    ensure_public_host(hostname, "Webhook")
    return raw


def validate_webhook_config(config: dict[str, Any] | None, credentials: dict[str, str] | None) -> dict[str, Any]:
    config = dict(config or {})
    credentials = dict(credentials or {})
    allowed = {"schema_version", "auth_mode", "receiver_deduplicates", "include_attachments"}
    if set(config) - allowed:
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
    with open(path, "rb") as source:
        while True:
            chunk = await asyncio.to_thread(source.read, 64 * 1024)
            if not chunk:
                break
            yield chunk


def _signature(key: bytes, event_id: str, timestamp: str, content_type: str, body: bytes | None, path: str | None) -> str:
    signer = hmac.new(key, f"{event_id}.{timestamp}.{content_type}.".encode("ascii"), hashlib.sha256)
    if body is not None:
        signer.update(body)
    elif path:
        with open(path, "rb") as source:
            for chunk in iter(lambda: source.read(256 * 1024), b""):
                signer.update(chunk)
    return signer.hexdigest()


class WebhookProvider:
    descriptor = ProviderDescriptor(
        key="webhook",
        name="Webhook",
        supports_links=True,
        supports_native_attachments=False,
        supports_binary_attachments=True,
    )

    def validate_secret(self, value: str) -> str:
        return validate_webhook_url(value)

    def validate_destination(self, value: str, config: dict[str, Any] | None, credentials: dict[str, str] | None) -> tuple[str, dict[str, Any]]:
        return validate_webhook_url(value), validate_webhook_config(config, credentials)

    async def send(
        self,
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
    ) -> dict[str, Any]:
        try:
            validate_webhook_url(secret)
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
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout, connect=5.0),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream("POST", secret, headers=headers, content=content) as response:
                    status_code = response.status_code
                    retry_after_value = response.headers.get("Retry-After")
        except httpx.ConnectTimeout as exc:
            raise DeliveryError("Could not connect to webhook before sending", kind="retryable") from exc
        except httpx.ConnectError as exc:
            raise DeliveryError("Could not connect to webhook before sending", kind="retryable") from exc
        except httpx.TimeoutException as exc:
            kind = "retryable" if validated["receiver_deduplicates"] else "unknown"
            raise DeliveryError("Webhook request timed out; acceptance may be unknown", kind=kind) from exc
        except httpx.RequestError as exc:
            kind = "retryable" if validated["receiver_deduplicates"] else "unknown"
            raise DeliveryError("Webhook request failed; acceptance may be unknown", kind=kind) from exc

        if 200 <= status_code < 300:
            return {"http_status": status_code, "event_id": event_id}
        if status_code == 429:
            from output.teams_workflow import parse_retry_after
            raise DeliveryError(
                "Webhook rejected the request due to throttling", kind="retryable", http_status=429,
                retry_after=parse_retry_after(retry_after_value),
            )
        if status_code >= 500 or status_code == 408:
            kind = "retryable" if validated["receiver_deduplicates"] else "unknown"
            raise DeliveryError(f"Webhook returned HTTP {status_code}; acceptance may be unknown", kind=kind, http_status=status_code)
        raise DeliveryError(f"Webhook rejected the request (HTTP {status_code})", kind="permanent", http_status=status_code)
