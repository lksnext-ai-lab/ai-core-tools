"""Provider-neutral contract for connector providers."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from connectors.core.inbound import InboundMessage, RawInboundRequest, VerifiedRequest
from connectors.core.messages import (
    AttachmentStager,
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


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class UpdatePolicy(StrEnum):
    REVALIDATE_ALL = "revalidate_all"  # every PATCH revalidates URL+config+credentials and persists the three
    ROTATE_URL_ONLY = "rotate_url_only"  # only a new webhook_url is validated/persisted


@dataclass(frozen=True)
class OutboundCapabilities:
    receiver_deduplication: bool = False  # provider.receiver_deduplicates(...) is consulted
    spooled_attachments: bool = False  # destination admits spooled/multipart attachments
    attachment_lease_seconds: int | None = None  # extended lease when includes_attachments(...)
    update_policy: UpdatePolicy = UpdatePolicy.ROTATE_URL_ONLY
    url_allows_fragment: bool = False


@dataclass(frozen=True)
class ProviderDescriptor:
    key: str
    name: str
    supports_links: bool = True
    supports_native_attachments: bool = False
    supports_binary_attachments: bool = False
    content_modes: tuple[str, ...] = ("result", "excerpt", "link_only")
    directions: frozenset[Direction] = frozenset({Direction.OUTBOUND})
    outbound: OutboundCapabilities | None = OutboundCapabilities()


@runtime_checkable
class OutboundProvider(Protocol):
    descriptor: ProviderDescriptor

    def validate_destination(
        self, url: str, public_config: Mapping[str, JsonValue] | None, credentials: Mapping[str, str] | None,
    ) -> ValidatedDestination: ...

    def ensure_same_endpoint(self, current_url: str, new_url: str) -> None: ...

    def includes_attachments(self, public_config: Mapping[str, JsonValue] | None) -> bool: ...

    def receiver_deduplicates(self, public_config: Mapping[str, JsonValue] | None) -> bool: ...

    def build_snapshot(self, destination: DestinationView) -> JsonDict: ...

    def snapshot_public_config(self, snapshot: Mapping[str, JsonValue]) -> JsonDict: ...

    def build_run_delivery(self, context: RunDeliveryContext) -> PreparedDelivery: ...

    def build_test_delivery(self, context: TestDeliveryContext, stager: AttachmentStager) -> PreparedDelivery: ...

    async def send(self, request: OutboundRequest) -> SendReceipt: ...

    def example_destination(self) -> DestinationExample: ...


@runtime_checkable
class InboundProvider(Protocol):
    descriptor: ProviderDescriptor

    def verify(self, raw: RawInboundRequest) -> VerifiedRequest: ...

    def parse(self, verified: VerifiedRequest) -> InboundMessage: ...
