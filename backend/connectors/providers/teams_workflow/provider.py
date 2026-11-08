"""Teams Workflows webhook provider using Adaptive Cards and authenticated links."""

from typing import Any
from urllib.parse import urlparse

import httpx
from utils.ssrf_guard import (
    FetchUnresolvableError,
    SsrfBlockedError,
    pinned_async_transport,
)

import connectors.core.http  # noqa: F401  (installs the httpx URL-redaction filter)
from connectors.core.contracts import ProviderDescriptor
from connectors.core.errors import DeliveryError
from connectors.core.http import ensure_public_host, parse_retry_after

ALLOWED_WEBHOOK_HOST_SUFFIXES = (
    ".logic.azure.com", ".logic.azure.us", ".logic.azure.cn", ".api.powerplatform.com",
)


def check_teams_workflow_url(value: str) -> str:
    """Structural checks only (no DNS): HTTPS, a Microsoft Power Automate host, port 443."""
    raw = (value or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Teams Workflow URL must be an HTTPS URL")
    if not parsed.hostname.lower().endswith(ALLOWED_WEBHOOK_HOST_SUFFIXES):
        raise ValueError("Teams Workflow URL must use a Microsoft Power Automate host")
    if parsed.port not in (None, 443):
        raise ValueError("Teams Workflow URL must use the standard HTTPS port")
    return raw


def validate_teams_workflow_url(value: str) -> str:
    """Require HTTPS and a public DNS target; webhook URLs are bearer credentials.

    Resolves DNS synchronously: call it from sync code only. Sends re-check the
    resolved address through the pinned transport instead.
    """
    raw = check_teams_workflow_url(value)
    ensure_public_host(urlparse(raw).hostname, "Teams Workflow")
    return raw


async def post_card(webhook_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send one card; do not follow redirects because the URL contains a credential."""
    try:
        check_teams_workflow_url(webhook_url)
        async with httpx.AsyncClient(
            transport=pinned_async_transport(), timeout=httpx.Timeout(20.0, connect=5.0),
            follow_redirects=False, trust_env=False,
        ) as client:
            response = await client.post(webhook_url, json=payload)
    except FetchUnresolvableError as exc:
        raise DeliveryError("Teams Workflow host could not be resolved", kind="retryable") from exc
    except SsrfBlockedError as exc:
        raise DeliveryError("Teams Workflow URL cannot target a private or reserved network", kind="permanent") from exc
    except httpx.ConnectTimeout as exc:
        raise DeliveryError("Timed out connecting to Teams Workflow", kind="retryable") from exc
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
        return validate_teams_workflow_url(value)

    async def send(self, secret: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await post_card(secret, payload)
