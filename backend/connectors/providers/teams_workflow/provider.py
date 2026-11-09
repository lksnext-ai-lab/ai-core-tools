"""Teams Workflows webhook provider using Adaptive Cards and authenticated links."""

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import httpx
from utils.ssrf_guard import (
    FetchUnresolvableError,
    SsrfBlockedError,
)

import connectors.core.http  # noqa: F401  (installs the httpx URL-redaction filter)
from connectors.core.contracts import (
    OutboundCapabilities,
    ProviderDescriptor,
    UpdatePolicy,
)
from connectors.core.errors import DeliveryError
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
from connectors.providers.teams_workflow.card import build_run_card, build_test_card

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


async def post_card(webhook_url: str, payload: dict[str, Any]) -> SendReceipt:
    """Send one card; do not follow redirects because the URL contains a credential."""
    try:
        check_teams_workflow_url(webhook_url)
        async with pinned_client(20.0) as client:
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
        outbound=OutboundCapabilities(update_policy=UpdatePolicy.ROTATE_URL_ONLY, url_allows_fragment=True),
    )

    def validate_secret(self, value: str) -> str:
        return validate_teams_workflow_url(value)

    def validate_destination(
        self, url: str, public_config: Mapping[str, JsonValue] | None, credentials: Mapping[str, str] | None,
    ) -> ValidatedDestination:
        url = validate_teams_workflow_url(url)
        if public_config or credentials:
            raise ValueError("Teams destinations do not accept webhook settings or credentials")
        return ValidatedDestination(url, {}, dict(credentials or {}))

    def ensure_same_endpoint(self, current_url: str, new_url: str) -> None:
        current, new = urlparse(current_url), urlparse(new_url)
        if (current.scheme, current.netloc, current.path) != (new.scheme, new.netloc, new.path):
            raise ValueError("Changing the Workflow or channel requires creating a new destination")

    def includes_attachments(self, public_config: Mapping[str, JsonValue] | None) -> bool:
        return False

    def receiver_deduplicates(self, public_config: Mapping[str, JsonValue] | None) -> bool:
        return False

    def build_snapshot(self, destination: DestinationView) -> JsonDict:
        return {
            "provider_key": destination.provider_key, "name": destination.name,
            "content_mode": destination.content_mode,
        }

    def snapshot_public_config(self, snapshot: Mapping[str, JsonValue]) -> JsonDict:
        return {}

    def build_run_delivery(self, context: RunDeliveryContext) -> PreparedDelivery:
        payload = build_run_card(context.message, content_mode=context.destination.content_mode)
        return PreparedDelivery(payload=payload, event_id=None, body_encoding=BodyEncoding.NONE)

    def build_test_delivery(self, context: TestDeliveryContext, stager: AttachmentStager) -> PreparedDelivery:
        payload = build_test_card(
            destination_name=context.destination.name, content_mode=context.destination.content_mode,
            base_url=context.base_url, now=context.now,
        )
        return PreparedDelivery(payload, None, BodyEncoding.NONE)

    async def send(self, request: OutboundRequest) -> SendReceipt:
        return await post_card(request.url, request.payload)

    def example_destination(self) -> DestinationExample:
        return DestinationExample(
            "https://prod-00.westeurope.logic.azure.com/workflows/example/triggers/manual/paths/invoke?sig=example",
            {}, {}, None,
        )
