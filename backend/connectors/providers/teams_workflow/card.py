"""Adaptive Card construction for the Teams Workflow provider."""

import base64
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from connectors.core.messages import JsonDict, RunMessage

MAX_CARD_BYTES = 24 * 1024
MAX_RESULT_CHARS = 5000
MAX_EXCERPT_CHARS = 1200
MATTIN_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "mattin-small.png"
MATTIN_LOGO_DATA_URI = "data:image/png;base64," + base64.b64encode(MATTIN_LOGO_PATH.read_bytes()).decode("ascii")


def build_adaptive_card(
    *, title: str, status: str, scheduled_time: str, result: str, view_url: str,
    files: list[dict[str, str]] | None = None, content_mode: str = "result",
) -> JsonDict:
    files = files or []
    limit = MAX_EXCERPT_CHARS if content_mode == "excerpt" else MAX_RESULT_CHARS
    result_text = result[:limit - 1].rstrip() + "…" if content_mode == "excerpt" and len(result) > limit else result
    if content_mode == "link_only":
        result_text = "The scheduled task has completed. Open the result to view its full output."
    elif len(result_text) > limit:
        result_text = result_text[:limit].rstrip() + "…"

    body: list[dict[str, Any]] = [
        {
            "type": "Container",
            "style": "emphasis",
            "items": [
                {
                    "type": "ColumnSet",
                    "verticalContentAlignment": "Center",
                    "columns": [
                        {
                            "type": "Column",
                            "width": "auto",
                            "verticalContentAlignment": "Center",
                            "items": [{
                                "type": "Image",
                                "url": MATTIN_LOGO_DATA_URI,
                                "size": "Small",
                                "altText": "Mattin AI",
                            }],
                        },
                        {
                            "type": "Column",
                            "width": "stretch",
                            "verticalContentAlignment": "Center",
                            "items": [
                                {"type": "TextBlock", "text": "MATTIN AI", "weight": "Bolder", "size": "Small", "color": "Accent", "spacing": "None"},
                                {"type": "TextBlock", "text": "Scheduled task", "size": "Small", "isSubtle": True, "spacing": "None"},
                            ],
                        },
                    ],
                },
                {"type": "TextBlock", "text": title[:255], "weight": "Bolder", "size": "Large", "wrap": True, "spacing": "Medium"},
            ],
        },
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
                "$schema": "https://adaptivecards.io/schemas/adaptive-card.json",
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
        if len(json.dumps(card, ensure_ascii=False).encode("utf-8")) > MAX_CARD_BYTES:
            content["actions"] = []
    return card


def build_run_card(message: RunMessage, *, content_mode: str) -> JsonDict:
    """Build the card for a finished run; never publishes ``file://`` references."""
    base = message.base_url
    result_url = f"{base}/apps/{message.app_id}/scheduled-tasks/{message.task_id}/runs/{message.run_id}"
    file_items: list[dict[str, str]] = []
    for item in message.output_files:
        file_id = item.get("file_id")
        if not file_id:
            continue
        file_url = f"{result_url}/files/{quote(str(file_id), safe='')}"
        file_items.append({"filename": str(item.get("filename") or "Output file"), "url": file_url})
    scheduled_time = message.scheduled_time
    if scheduled_time.tzinfo is None:
        scheduled_time = scheduled_time.replace(tzinfo=UTC)
    else:
        scheduled_time = scheduled_time.astimezone(UTC)
    result_text = message.output_text
    for item in message.output_files:
        file_id = str(item.get("file_id") or "")
        filename = str(item.get("filename") or "output file")
        for identifier in (file_id, filename):
            if identifier:
                result_text = result_text.replace(f"file://{identifier}", filename)
    # Never place local sandbox/file references in a message. The card links below
    # point to the authenticated Mattin AI file route instead.
    result_text = re.sub(r"file://[^\s\])}]+", "[output file]", result_text)
    return build_adaptive_card(
        title=message.task_name,
        status=message.run_status,
        scheduled_time=scheduled_time.isoformat(),
        result=result_text,
        view_url=result_url,
        files=file_items,
        content_mode=content_mode,
    )


def build_test_card(*, destination_name: str, content_mode: str, base_url: str, now: datetime) -> JsonDict:
    """Build the connection-test card."""
    return build_adaptive_card(
        title=f"{destination_name}: connection test", status="test", scheduled_time=now.isoformat(),
        result="This is a test notification from Mattin AI.", view_url=base_url, content_mode=content_mode,
    )
