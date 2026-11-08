"""JSON event construction for the generic webhook provider."""

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from urllib.parse import quote

from connectors.core.messages import ArtifactDict, JsonDict, RunMessage

_MANIFEST_KEYS = ("file_id", "filename", "content_type", "size_bytes", "sha256", "part_name")


def attachment_manifest(artifacts: Sequence[ArtifactDict]) -> list[JsonDict]:
    """Return the public attachment manifest (no spool object keys)."""
    return [{key: item[key] for key in _MANIFEST_KEYS} for item in artifacts]


def build_run_event(
    message: RunMessage, *, content_mode: str, event_id: str, artifacts: Sequence[ArtifactDict],
) -> JsonDict:
    """Build the ``task.run.succeeded`` event for a finished run."""
    result_url = f"{message.base_url}/apps/{message.app_id}/scheduled-tasks/{message.task_id}/runs/{message.run_id}"
    files = []
    for item in message.output_files:
        file_id = str(item.get("file_id") or "")
        if not file_id:
            continue
        filename = str(item.get("filename") or "Output file")
        files.append({
            "file_id": file_id,
            "filename": filename,
            "url": f"{result_url}/files/{quote(file_id, safe='')}",
        })
    text = message.output_text
    for item in message.output_files:
        file_id = str(item.get("file_id") or "")
        filename = str(item.get("filename") or "output file")
        for marker in (file_id, filename):
            if marker:
                text = text.replace(f"file://{marker}", filename)
    text = re.sub(r"file://[^\s\])}]+", "[output file]", text)
    mode = content_mode
    text_limit = 4000 if mode == "excerpt" else 100_000
    text_truncated = len(text) > text_limit
    visible_files = files[:50]
    files_truncated = len(visible_files) < len(files)
    visible_text: str | None
    if mode == "link_only":
        visible_text = None
        visible_files = []
        files_truncated = False
        text_truncated = False
    else:
        visible_text = text[:text_limit]
    occurred_at = message.finished_at or datetime.now(UTC)
    scheduled_at = message.scheduled_time
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=UTC)
    return {
        "schema_version": "1",
        "event_id": event_id,
        "event_type": "task.run.succeeded",
        "occurred_at": occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "app": {"id": message.app_id},
        "task": {"id": message.task_id, "name": message.task_name},
        "run": {
            "id": message.run_id,
            "status": message.run_status,
            "scheduled_at": scheduled_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "completed_at": occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        },
        "content": {
            "mode": mode,
            "text": visible_text,
            "text_truncated": text_truncated,
            "files_truncated": files_truncated,
            "files": visible_files,
        },
        "attachments": attachment_manifest(artifacts),
        "links": {"result": result_url},
    }


def build_test_event(*, app_id: int, content_mode: str, event_id: str, base_url: str, now: datetime) -> JsonDict:
    """Build the ``destination.test`` event."""
    return {
        "schema_version": "1", "event_id": event_id, "event_type": "destination.test",
        "occurred_at": now.isoformat().replace("+00:00", "Z"),
        "app": {"id": app_id}, "task": None, "run": None,
        "content": {"mode": content_mode,
                    "text": None if content_mode == "link_only" else "This is a test notification from Mattin AI.",
                    "text_truncated": False, "files_truncated": False, "files": []},
        "attachments": [], "links": {"result": base_url},
    }
