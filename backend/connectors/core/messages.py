"""Provider-neutral message types shared by connector providers and the delivery service."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict

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
