"""Helpers shared by the golden tests: comparison, normalisation, scenario builders."""

import base64
import hashlib
import hmac
import json
import os
import re
import warnings
from datetime import datetime
from pathlib import Path

from models.output_delivery import OutputDelivery, OutputDeliveryAttempt, ScheduledTaskOutputBinding
from models.scheduled_task import ScheduledTask, ScheduledTaskRun

FIXTURES = Path(__file__).parent / "fixtures"

# Synthetic secrets only.
HMAC_KEY = b"k" * 32
HMAC_SECRET = base64.b64encode(HMAC_KEY).decode()
BEARER_TOKEN = "tok-123"
TEAMS_URL = "https://prod-00.westeurope.logic.azure.com/workflows/synthetic-flow/triggers/manual/paths/invoke?sig=SYNTHETIC-SIG"
WEBHOOK_URL = "https://hooks.example.com/mattin/synthetic"

FINISHED_AT = datetime(2026, 5, 4, 8, 30, 15)
SCHEDULED_TIME = datetime(2026, 5, 4, 8, 0, 0)

_LOGO = re.compile(r"data:image/png;base64,[A-Za-z0-9+/=]+")
_TS = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?"
# Anchored on the two fields that read the wall clock; any other timestamp is left intact.
_NOW_WEBHOOK = re.compile(r'("occurred_at":"?)' + _TS + r'Z(")')
_NOW_TEAMS = re.compile(r'("title":"Scheduled","value":")' + _TS + r'\+00:00(")')


def _mask_logo(text: str) -> str:
    return _LOGO.sub(lambda m: f"<mattin-logo sha256={hashlib.sha256(m.group().encode()).hexdigest()[:16]}>", text)


def to_jsonable(value):
    """Bytes become utf-8 text when decodable, otherwise base64 + sha256."""
    if isinstance(value, bytes):
        try:
            return _mask_logo(value.decode("utf-8"))
        except UnicodeDecodeError:
            return {"base64": base64.b64encode(value).decode(), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, str):
        return _mask_logo(value)
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    return value


def check_golden(name: str, data) -> None:
    normalized = json.loads(json.dumps(to_jsonable(data), sort_keys=True, ensure_ascii=False))
    path = FIXTURES / f"{name}.json"
    if os.getenv("GOLDEN_UPDATE") == "1":
        FIXTURES.mkdir(exist_ok=True)
        path.write_text(json.dumps(normalized, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        warnings.warn(f"GOLDEN_UPDATE=1: rewrote {path.name}; this is NOT a comparison run", stacklevel=2)
        return
    assert path.exists(), f"Missing golden fixture {path.name}; generate with GOLDEN_UPDATE=1"
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert normalized == expected


def signature(key: bytes, event_id: str, timestamp: str, content_type: str, body: bytes) -> str:
    return "v1=" + hmac.new(key, f"{event_id}.{timestamp}.{content_type}.".encode() + body, hashlib.sha256).hexdigest()


def verify_and_mask_signature(request: dict, key: bytes) -> dict:
    """Recompute the HMAC over the recorded bytes; replace the literal value by a marker."""
    headers = dict(request["headers"])
    if "x-mattin-signature" in headers:
        expected = signature(key, headers["x-mattin-event-id"], headers["x-mattin-timestamp"],
                             headers["content-type"], request["body"])
        assert headers["x-mattin-signature"] == expected
        headers["x-mattin-signature"] = "<verified-hmac>"
    return {**request, "headers": headers}


def mask_now(request: dict) -> dict:
    """test_destination reads the wall clock: mask only its two timestamp fields."""
    body = request["body"]
    # Tautological on its own (httpx computes it from the body); the full body
    # comparison against the fixture is what actually guards the content.
    assert request["headers"]["content-length"] == str(len(body))
    text = body.decode("utf-8")
    text = _NOW_WEBHOOK.sub(r"\1<now:Z>\2", text)
    text = _NOW_TEAMS.sub(r"\1<now:+00:00>\2", text)
    headers = {**request["headers"], "content-length": "<len>"}
    return {**request, "body": text.encode("utf-8"), "headers": headers}


def make_task_and_run(db, *, output_text, output_files):
    task = ScheduledTask(
        id=1, name="Daily report", agent_id=1, app_id=1, created_by=1,
        orchestrator_schedule_name="golden-task", cron_expression="0 8 * * *",
    )
    run = ScheduledTaskRun(
        id=1, scheduled_task_id=1, orchestrator_run_id="golden-run", scheduled_time=SCHEDULED_TIME,
        finished_at=FINISHED_AT, status="succeeded", output_text=output_text, output_files=output_files,
    )
    db.add_all([task, run])
    db.commit()
    return task, run


def bind(db, destination, task_id=1):
    db.add(ScheduledTaskOutputBinding(scheduled_task_id=task_id, destination_id=destination.id))
    db.commit()


def persisted_state(db, spool: Path) -> list[dict]:
    """Everything stored on the outbox rows, except time-dependent columns (expires_at, ...)."""
    out = []
    for delivery in db.query(OutputDelivery).order_by(OutputDelivery.id).all():
        body_file = None
        if delivery.request_body_path:
            body_file = (spool / delivery.request_body_path).read_bytes()
        out.append({
            "destination_snapshot": delivery.destination_snapshot,
            "payload": delivery.payload,
            "request_body": delivery.request_body,
            "request_body_path": delivery.request_body_path,
            "request_body_file": body_file,
            "request_body_size": delivery.request_body_size,
            "request_body_sha256": delivery.request_body_sha256,
            "status": delivery.status,
            "error_summary": delivery.error_summary,
        })
    return out


def final_state(db) -> list[dict]:
    db.expire_all()
    out = []
    for delivery in db.query(OutputDelivery).order_by(OutputDelivery.id).all():
        attempts = db.query(OutputDeliveryAttempt).filter_by(delivery_id=delivery.id).order_by(OutputDeliveryAttempt.id).all()
        out.append({
            "status": delivery.status,
            "receipt": delivery.receipt,
            "attempt_count": delivery.attempt_count,
            "error_summary": delivery.error_summary,
            "request_body_cleared": delivery.request_body is None and delivery.request_body_path is None,
            "attempts": [{"attempt_number": a.attempt_number, "status": a.status, "http_status": a.http_status,
                          "error_summary": a.error_summary} for a in attempts],
        })
    return out
