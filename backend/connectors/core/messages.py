"""Provider-neutral message types shared by connector providers and the delivery service."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import NotRequired, Protocol, Required, TypedDict

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonDict = dict[str, JsonValue]


class ArtifactDict(TypedDict):
    """One staged output file that can travel with a delivery."""

    file_id: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    part_name: str
    object_key: str


@dataclass(frozen=True)
class RunMessage:
    """Snapshot of a finished scheduled-task run, independent of ORM models."""

    app_id: int
    task_id: int
    task_name: str
    run_id: int
    run_status: str
    scheduled_time: datetime
    finished_at: datetime | None
    output_text: str
    output_files: tuple[Mapping[str, JsonValue], ...]
    base_url: str


@dataclass(frozen=True)
class DestinationView:
    """What a provider may know about a destination: no URL and no credentials."""

    app_id: int
    name: str
    provider_key: str
    content_mode: str
    public_config: Mapping[str, JsonValue]


@dataclass(frozen=True)
class RunDeliveryContext:
    message: RunMessage
    destination: DestinationView
    artifacts: tuple[ArtifactDict, ...]


@dataclass(frozen=True)
class TestDeliveryContext:
    # Not a test class despite the name.
    __test__ = False

    destination: DestinationView
    base_url: str
    now: datetime


class BodyEncoding(StrEnum):
    NONE = "none"  # the provider serializes the JSON payload itself
    JSON = "json"  # prepared canonical JSON body
    MULTIPART = "multipart"  # prepared multipart/form-data spool file


@dataclass(frozen=True)
class PreparedDelivery:
    payload: JsonDict = field(repr=False)
    event_id: str | None
    body_encoding: BodyEncoding
    attachments: tuple[ArtifactDict, ...] = ()
    requires_attachments: bool = False


@dataclass(frozen=True)
class ValidatedDestination:
    url: str = field(repr=False)
    public_config: JsonDict
    credentials: dict[str, str] = field(repr=False)


@dataclass(frozen=True)
class DestinationExample:
    url: str = field(repr=False)
    public_config: JsonDict
    credentials: dict[str, str] = field(repr=False)
    deduplicating_public_config: JsonDict | None


@dataclass(frozen=True)
class OutboundRequest:
    """One send attempt. ``url``, ``credentials`` and ``body`` stay out of ``repr``."""

    url: str = field(repr=False)
    payload: JsonDict = field(repr=False)
    public_config: Mapping[str, JsonValue]
    credentials: Mapping[str, str] = field(repr=False)
    event_id: str | None
    attempt_number: int
    content_type: str
    body: bytes | None = field(repr=False)
    body_path: str | None


class SendReceipt(TypedDict, total=False):
    """Persisted as ``OutputDelivery.receipt`` and expanded by the test endpoint."""

    http_status: Required[int]
    event_id: NotRequired[str]


class AttachmentStager(Protocol):
    def stage(
        self, relative_name: str, data: bytes, *, file_id: str, filename: str, content_type: str, part_name: str,
    ) -> ArtifactDict: ...
