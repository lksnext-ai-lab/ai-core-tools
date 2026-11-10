"""Fictitious bidirectional provider proving a new connector needs only ``connectors.core`` (AC-11).

It is never registered globally: tests register it with ``monkeypatch`` only.
"""

import hmac
from collections.abc import Mapping
from typing import Literal, cast
from urllib.parse import urlparse

import httpx
from connectors.core.contracts import (
    Direction,
    OutboundCapabilities,
    ProviderDescriptor,
    UpdatePolicy,
)
from connectors.core.errors import DeliveryError
from connectors.core.http import ensure_public_host, parse_retry_after, pinned_client
from connectors.core.inbound import (
    BaseInboundProvider,
    InboundMessage,
    RawInboundRequest,
    VerifiedRequest,
)
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
from connectors.core.settings import DestinationSettingsBase
from pydantic import BaseModel, ConfigDict, SecretStr, StrictBool
from utils.ssrf_guard import FetchUnresolvableError, SsrfBlockedError

_MODEL_CONFIG = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
PUBLIC_KEYS = frozenset({"prefix", "receiver_deduplicates"})


class DummyPublicConfig(BaseModel):
    model_config = _MODEL_CONFIG

    prefix: str = "echo"
    receiver_deduplicates: StrictBool = False


class DummyCredentials(BaseModel):
    model_config = _MODEL_CONFIG

    api_key: SecretStr


class DummySettings(DestinationSettingsBase):
    provider_key: Literal["dummy_echo"] = "dummy_echo"
    public_config: DummyPublicConfig
    credentials: DummyCredentials

    def public_config_json(self) -> JsonDict:
        return dict(self.public_config.model_dump())

    def credentials_json(self) -> dict[str, str]:
        return {"api_key": self.credentials.api_key.get_secret_value()}


class DummyEchoProvider(BaseInboundProvider):
    descriptor = ProviderDescriptor(
        key="dummy_echo",
        name="Dummy echo",
        directions=frozenset({Direction.INBOUND, Direction.OUTBOUND}),
        outbound=OutboundCapabilities(receiver_deduplication=True, update_policy=UpdatePolicy.REVALIDATE_ALL),
    )
    TEST_INBOUND_TOKEN = "dummy-inbound-token"  # test-only value, never a real secret

    def __init__(self, inbound_token: str = TEST_INBOUND_TOKEN) -> None:
        """``inbound_token`` is the shared secret expected in ``x-echo-token``; the default is for tests only.

        An empty token means "not configured": every inbound request is then rejected.
        """
        self._inbound_token = inbound_token

    # ---- outbound -------------------------------------------------------------------------------
    @staticmethod
    def _check_url(value: str) -> str:
        raw = (value or "").strip()
        parsed = urlparse(raw)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("Dummy URL must be an HTTPS URL without user info or a fragment")
        if parsed.port not in (None, 443):
            raise ValueError("Dummy URL must use port 443")
        return raw

    def validate_destination(
        self, url: str, public_config: Mapping[str, JsonValue] | None, credentials: Mapping[str, str] | None,
    ) -> ValidatedDestination:
        url = self._check_url(url)
        ensure_public_host(urlparse(url).hostname or "", "Dummy")
        settings = self.parse_settings(public_config, credentials)
        return ValidatedDestination(url, settings.public_config_json(), settings.credentials_json())

    def parse_settings(
        self, public_config: Mapping[str, JsonValue] | None, credentials: Mapping[str, str] | None,
    ) -> DestinationSettingsBase:
        return self._parse(public_config, credentials)

    @staticmethod
    def _parse(
        public_config: Mapping[str, JsonValue] | None, credentials: Mapping[str, str] | None,
    ) -> DummySettings:
        try:
            return DummySettings(
                provider_key="dummy_echo",
                public_config=DummyPublicConfig.model_validate(dict(public_config or {})),
                credentials=DummyCredentials.model_validate(dict(credentials or {})),
            )
        except ValueError:
            pass
        raise ValueError("Invalid dummy destination settings")

    def ensure_same_endpoint(self, current_url: str, new_url: str) -> None:
        if urlparse(current_url)[:3] != urlparse(new_url)[:3]:
            raise ValueError("Changing a dummy endpoint requires creating a new destination")

    def includes_attachments(self, public_config: Mapping[str, JsonValue] | None) -> bool:
        return False

    def receiver_deduplicates(self, public_config: Mapping[str, JsonValue] | None) -> bool:
        return (public_config or {}).get("receiver_deduplicates") is True

    def build_snapshot(self, destination: DestinationView) -> JsonDict:
        return {
            **dict(destination.public_config or {}),
            "provider_key": destination.provider_key, "name": destination.name,
            "content_mode": destination.content_mode,
        }

    def snapshot_public_config(self, snapshot: Mapping[str, JsonValue]) -> JsonDict:
        return {key: value for key, value in snapshot.items() if key in PUBLIC_KEYS}

    def build_run_delivery(self, context: RunDeliveryContext) -> PreparedDelivery:
        payload: JsonDict = {
            "event_id": f"run-{context.message.run_id}", "event_type": "task.run.finished",
            "text": context.message.output_text,
        }
        return PreparedDelivery(payload, f"run-{context.message.run_id}", BodyEncoding.JSON)

    def build_test_delivery(self, context: TestDeliveryContext, stager: AttachmentStager) -> PreparedDelivery:
        payload: JsonDict = {"event_id": "test", "event_type": "destination.test", "text": context.destination.name}
        return PreparedDelivery(payload, "test", BodyEncoding.JSON)

    async def send(self, request: OutboundRequest) -> SendReceipt:
        try:
            self._check_url(request.url)
            settings = self._parse(dict(request.public_config), dict(request.credentials))
        except ValueError as exc:
            raise DeliveryError(str(exc), kind="permanent") from exc
        dedup = settings.public_config.receiver_deduplicates
        headers = {
            "Content-Type": request.content_type,
            "Authorization": f"Bearer {settings.credentials.api_key.get_secret_value()}",
        }
        if request.event_id:
            headers["Idempotency-Key"] = request.event_id
        try:
            async with pinned_client(20.0) as client:
                response = await client.post(request.url, headers=headers, content=request.body or b"")
        except FetchUnresolvableError as exc:
            raise DeliveryError("Dummy host could not be resolved", kind="retryable") from exc
        except SsrfBlockedError as exc:
            raise DeliveryError("Dummy URL cannot target a private or reserved network", kind="permanent") from exc
        except (httpx.ConnectTimeout, httpx.ConnectError) as exc:
            raise DeliveryError("Could not connect to dummy receiver", kind="retryable") from exc
        except httpx.RequestError as exc:  # includes read timeouts: delivery may have happened
            raise DeliveryError(
                "Dummy request failed; acceptance may be unknown", kind="retryable" if dedup else "unknown",
            ) from exc
        status = response.status_code
        if 200 <= status < 300:
            return {"http_status": status}
        if status == 429:
            raise DeliveryError(
                "Dummy receiver throttled the request", kind="retryable", http_status=429,
                retry_after=parse_retry_after(response.headers.get("Retry-After")),
            )
        if status >= 500 or status == 408:
            raise DeliveryError(
                f"Dummy receiver returned HTTP {status}", kind="retryable" if dedup else "unknown", http_status=status,
            )
        raise DeliveryError(f"Dummy receiver rejected the request (HTTP {status})", kind="permanent", http_status=status)

    def example_destination(self) -> DestinationExample:
        config: JsonDict = {"prefix": "echo", "receiver_deduplicates": False}
        return DestinationExample(
            "https://echo.example.com/hook/abc?sig=dummy-sig-0123456789", config, {"api_key": "dummy-api-key-0123456789"},
            {**config, "receiver_deduplicates": True},
        )

    # ---- inbound --------------------------------------------------------------------------------
    def _authenticate(self, raw: RawInboundRequest) -> Mapping[str, JsonValue]:
        if not self._inbound_token:
            raise PermissionError("inbound token not configured")
        supplied = raw.headers.get("x-echo-token", "")
        if not hmac.compare_digest(supplied.encode(), self._inbound_token.encode()):
            raise PermissionError("bad token")
        return {"sender": raw.headers.get("x-echo-sender", "anonymous")}

    def _parse_verified(self, verified: VerifiedRequest) -> InboundMessage:
        return InboundMessage(
            provider_key=verified.provider_key, external_conversation_id="echo-conversation",
            sender_id=str(cast(Mapping[str, JsonValue], verified.claims)["sender"]), text=verified.request.body.decode(), attachments=(), event_id=None,
        )
