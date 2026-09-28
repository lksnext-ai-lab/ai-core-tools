"""Teams Workflows webhook provider using Adaptive Cards and authenticated links."""

import ipaddress
import json
import socket
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from output.contracts import ProviderDescriptor


MAX_CARD_BYTES = 24 * 1024
MAX_RESULT_CHARS = 5000


class DeliveryError(Exception):
    def __init__(self, message: str, *, kind: str = "permanent", http_status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.http_status = http_status
        self.retry_after = retry_after


def validate_webhook_url(value: str) -> str:
    """Require HTTPS and a public DNS target; webhook URLs are bearer credentials."""
    raw = (value or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Teams Workflow URL must be an HTTPS URL")
    if parsed.port not in (None, 443):
        raise ValueError("Teams Workflow URL must use the standard HTTPS port")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Teams Workflow host could not be resolved") from exc
    if not addresses:
        raise ValueError("Teams Workflow host could not be resolved")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Teams Workflow URL cannot target a private or reserved network")
    return raw


def build_adaptive_card(
    *, title: str, status: str, scheduled_time: str, result: str, view_url: str,
    files: list[dict[str, str]] | None = None, content_mode: str = "result",
) -> dict[str, Any]:
    files = files or []
    result_text = result if content_mode == "result" else result[:MAX_RESULT_CHARS]
    if content_mode == "link_only":
        result_text = "The scheduled task has completed. Open the result to view its full output."
    elif len(result_text) > MAX_RESULT_CHARS:
        result_text = result_text[:MAX_RESULT_CHARS].rstrip() + "…"

    body: list[dict[str, Any]] = [
        {"type": "TextBlock", "text": title[:255], "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "FactSet", "facts": [
            {"title": "Status", "value": status[:40]},
            {"title": "Scheduled", "value": scheduled_time[:80]},
        ]},
    ]
    if result_text:
        body.append({"type": "TextBlock", "text": result_text, "wrap": True})
    actions = [{"type": "Action.OpenUrl", "title": "View result", "url": view_url}]
    if files:
        body.append({"type": "TextBlock", "text": "Files: " + ", ".join(item["filename"] for item in files[:20]), "wrap": True})
        actions.extend({"type": "Action.OpenUrl", "title": item["filename"][:80], "url": item["url"]} for item in files[:4])
    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": body,
                "actions": actions,
            },
        }],
    }
    if len(json.dumps(card, ensure_ascii=False).encode("utf-8")) > MAX_CARD_BYTES:
        # File and excerpt overflow should not make a delivery silently fail.
        content = card["attachments"][0]["content"]
        content["body"] = body[:2] + [{
            "type": "TextBlock", "text": "The output is too large to include here. Open the result to view it.", "wrap": True,
        }]
        content["actions"] = actions[:1]
    return card


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


async def post_card(webhook_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send one card; do not follow redirects because the URL contains a credential."""
    try:
        validate_webhook_url(webhook_url)
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0), follow_redirects=False, trust_env=False) as client:
            response = await client.post(webhook_url, json=payload)
    except httpx.ConnectError as exc:
        raise DeliveryError("Could not connect to Teams Workflow", kind="retryable") from exc
    except httpx.TimeoutException as exc:
        # A read timeout can happen after Power Automate accepted the payload.
        raise DeliveryError("Teams Workflow response timed out; posting outcome is unknown", kind="unknown") from exc
    except httpx.RequestError as exc:
        raise DeliveryError("Teams Workflow request failed; posting outcome is unknown", kind="unknown") from exc
    except ValueError as exc:
        raise DeliveryError(str(exc), kind="permanent") from exc

    if 200 <= response.status_code < 300:
        return {"http_status": response.status_code}
    if response.status_code == 429:
        raise DeliveryError("Teams Workflow throttled the request", kind="retryable", http_status=429,
                            retry_after=parse_retry_after(response.headers.get("Retry-After")))
    if response.status_code >= 500:
        # A server error does not prove whether a flow already accepted the event.
        raise DeliveryError(f"Teams Workflow returned HTTP {response.status_code}; posting outcome is unknown", kind="unknown", http_status=response.status_code)
    # Do not retain provider response bodies: they can contain sensitive workflow details.
    raise DeliveryError(f"Teams Workflow rejected the request (HTTP {response.status_code})", kind="permanent", http_status=response.status_code)


class TeamsWorkflowProvider:
    """First adapter registered behind the provider-neutral output contract."""

    descriptor = ProviderDescriptor(
        key="teams_workflow",
        name="Microsoft Teams channel",
        supports_links=True,
        supports_native_attachments=False,
    )

    def validate_secret(self, value: str) -> str:
        return validate_webhook_url(value)

    async def send(self, secret: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await post_card(secret, payload)
