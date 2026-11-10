"""CB-3 (FR-15): one rule for an abandoned ``sending`` delivery, shared by both recovery paths."""

import ast
import itertools
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from models.output_delivery import (
    OutputDelivery,
    OutputDeliveryAttempt,
    ScheduledTaskOutputBinding,
)
from scheduling import output_delivery
from services.output_channels import delivery_policy, delivery_processor
from services.output_channels.delivery_policy import (
    MAX_ATTEMPTS,
    classify_stale_sending,
)
from services.output_channels.delivery_processor import process_delivery

from .factories import make_destination, make_run, make_task

NOW = datetime(2026, 10, 1, 12, 0)
RETRY_MSG = "Webhook worker stopped during an idempotent request; retry scheduled."
UNKNOWN_MSG = "Worker stopped while the external request was in flight; verify receipt before resending."

PROVIDER_KEYS = ["webhook", "teams_workflow", None, "retired_provider"]
DEDUPE = [True, False, None]
ATTEMPTS = [MAX_ATTEMPTS - 1, MAX_ATTEMPTS]
EXPIRY = {"expired": NOW - timedelta(hours=1), "live": NOW + timedelta(hours=1), "none": None}

MATRIX = [
    pytest.param(key, dedupe, attempts, expiry, id=f"{key}-dedupe_{dedupe}-attempts_{attempts}-{expiry}")
    for key, dedupe, attempts, expiry in itertools.product(PROVIDER_KEYS, DEDUPE, ATTEMPTS, EXPIRY)
]


def _snapshot(key, dedupe):
    snapshot = {}
    if key is not None:
        snapshot["provider_key"] = key
    if dedupe is not None:
        snapshot["receiver_deduplicates"] = dedupe
    return snapshot


def _expected(key, dedupe, attempts, expiry):
    retry = key == "webhook" and dedupe is True and attempts < MAX_ATTEMPTS and expiry != "expired"
    return ("retry_wait", RETRY_MSG) if retry else ("unknown", UNKNOWN_MSG)


def test_matrix_has_72_cases():
    assert len(MATRIX) == 72


# Non-object snapshots (DB tampering) and non-string provider keys must classify as unknown, never raise.
ODD = [
    pytest.param(["x"], id="list-snapshot"),
    pytest.param("text", id="string-snapshot"),
    pytest.param({"provider_key": 1, "receiver_deduplicates": True}, id="non-string-provider-key"),
]


@pytest.fixture
def clock(monkeypatch):
    """One fixed clock for the pure function and both recovery paths (patched where it is used)."""
    monkeypatch.setattr(delivery_processor, "utcnow_naive", lambda: NOW)
    monkeypatch.setattr(output_delivery, "utcnow_naive", lambda: NOW)
    return NOW


@pytest.fixture
def sessions(outbox, monkeypatch):
    monkeypatch.setattr(output_delivery, "SessionLocal", outbox)
    monkeypatch.setattr(output_delivery, "enqueue_delivery", lambda *_: None)
    with outbox() as db:
        db.add_all([make_task(), make_run(), make_destination(1)])
        db.add(ScheduledTaskOutputBinding(id=1, scheduled_task_id=1, destination_id=1))
        db.commit()
    return outbox


def _add_stale(sessions, snapshot, attempts, expires_at, event_type="succeeded"):
    with sessions() as db:
        delivery = OutputDelivery(
            run_id=1, binding_id=1, destination_id=1, event_type=event_type, status="sending",
            lease_until=datetime(2020, 1, 1), attempt_count=attempts, expires_at=expires_at,
            destination_snapshot=snapshot,
        )
        db.add(delivery)
        db.flush()
        db.add(OutputDeliveryAttempt(delivery_id=delivery.id, attempt_number=attempts, status="sending"))
        db.commit()
        return delivery.id


def _read(sessions, delivery_id):
    with sessions() as db:
        delivery = db.get(OutputDelivery, delivery_id)
        attempt = delivery.attempts[-1]
        return {
            "status": delivery.status, "error_summary": delivery.error_summary,
            "lease_until": delivery.lease_until, "next_attempt_at": delivery.next_attempt_at,
            "attempt": (attempt.status, attempt.error_summary, attempt.finished_at is not None),
        }


@pytest.mark.parametrize("key, dedupe, attempts, expiry", MATRIX)
async def test_stale_sending_rule_is_identical_on_both_paths(sessions, clock, key, dedupe, attempts, expiry):
    status, message = _expected(key, dedupe, attempts, expiry)
    snapshot = _snapshot(key, dedupe)
    expires_at = EXPIRY[expiry]
    # (a) pure function
    outcome = classify_stale_sending(snapshot, attempt_count=attempts, expires_at=expires_at, now=NOW)
    assert (outcome.status, outcome.error_summary) == (status, message)
    assert (outcome.next_attempt_at == NOW + timedelta(seconds=30)) is (status == "retry_wait")
    if status == "unknown":
        assert outcome.next_attempt_at is None

    # (b) / (c) identical rows; the reconciler row needs another event_type because
    # (run_id, binding_id, event_type) is unique.
    via_process = _add_stale(sessions, snapshot, attempts, expires_at)
    via_reconciler = _add_stale(sessions, snapshot, attempts, expires_at, event_type="other")

    await process_delivery(via_process, 0)
    await output_delivery._reconcile_pending_deliveries()

    _assert_same(sessions, via_process, via_reconciler, status, message)


def _assert_same(sessions, via_process, via_reconciler, status, message):
    first, second = _read(sessions, via_process), _read(sessions, via_reconciler)
    assert (first["status"], first["error_summary"]) == (second["status"], second["error_summary"]) == (status, message)
    assert first["attempt"] == second["attempt"] == (status, message, True)
    assert first["lease_until"] is None and second["lease_until"] is None
    assert (first["next_attempt_at"] is not None) is (second["next_attempt_at"] is not None) is (status == "retry_wait")


@pytest.mark.parametrize("snapshot", ODD)
async def test_malformed_snapshots_are_unknown_on_both_paths(sessions, clock, snapshot):
    outcome = classify_stale_sending(snapshot, attempt_count=1, expires_at=None, now=NOW)
    assert (outcome.status, outcome.error_summary, outcome.next_attempt_at) == ("unknown", UNKNOWN_MSG, None)

    via_process = _add_stale(sessions, snapshot, 1, None)
    via_reconciler = _add_stale(sessions, snapshot, 1, None, event_type="other")
    await process_delivery(via_process, 0)
    await output_delivery._reconcile_pending_deliveries()
    _assert_same(sessions, via_process, via_reconciler, "unknown", UNKNOWN_MSG)


async def test_both_paths_call_the_shared_rule(sessions, clock, monkeypatch):
    calls = []
    real = delivery_policy.apply_stale_sending

    def spy(delivery, now):
        calls.append(delivery.id)
        real(delivery, now)

    monkeypatch.setattr(delivery_policy, "apply_stale_sending", spy)
    snapshot = {"provider_key": "webhook", "receiver_deduplicates": True}
    via_process = _add_stale(sessions, snapshot, 1, None)
    via_reconciler = _add_stale(sessions, snapshot, 1, None, event_type="other")

    await process_delivery(via_process, 0)
    assert calls == [via_process]
    await output_delivery._reconcile_pending_deliveries()
    assert calls == [via_process, via_reconciler]


async def test_reconciler_expired_stale_sending_is_unknown_and_not_enqueued(sessions, clock, monkeypatch):
    queued = []
    monkeypatch.setattr(output_delivery, "enqueue_delivery", lambda delivery_id, generation: queued.append(delivery_id))
    delivery_id = _add_stale(
        sessions, {"provider_key": "webhook", "receiver_deduplicates": True}, 1, NOW - timedelta(hours=1),
    )

    await output_delivery._reconcile_pending_deliveries()

    row = _read(sessions, delivery_id)
    assert (row["status"], row["error_summary"]) == ("unknown", UNKNOWN_MSG)
    assert queued == []


# --- AC-22 structural guard (ast based) ---------------------------------------------------

BACKEND = Path(output_delivery.__file__).resolve().parents[1]
PROCESSOR = BACKEND / "services" / "output_channels" / "delivery_processor.py"
RECONCILER = BACKEND / "scheduling" / "output_delivery.py"
GUARDED = [RECONCILER, *sorted((BACKEND / "services" / "output_channels").glob("*.py"))]
STALE_FRAGMENTS = ("idempotent request; retry scheduled", "verify receipt before resending")


def _is_attempt_count(node: ast.expr) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "attempt_count") or (
        isinstance(node, ast.Name) and node.id == "attempt_count"
    )


def _find_violations(source: str, *, is_policy: bool) -> list[str]:
    """Second copies of the stale-sending rule: ``attempt_count < <number>``, the rule texts, the dedupe flag."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare) and any(isinstance(op, (ast.Lt, ast.LtE)) for op in node.ops):
            operands = [node.left, *node.comparators]
            if any(_is_attempt_count(o) for o in operands) and any(
                isinstance(o, ast.Constant) and isinstance(o.value, (int, float)) for o in operands
            ):
                found.append("attempt_count < number")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and not is_policy:
            if "receiver_deduplicates" in node.value:
                found.append("receiver_deduplicates")
            if any(fragment in node.value for fragment in STALE_FRAGMENTS):
                found.append("stale summary text")
    return found


def _calls_apply_stale_sending(source: str) -> bool:
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "apply_stale_sending"
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "delivery_policy"
        for n in ast.walk(ast.parse(source))
    )


OLD_RECONCILER_BLOCK = """
snapshot = item.destination_snapshot or {}
retry_deduplicated = (
    delivery_policy.receiver_can_deduplicate(snapshot.get("provider_key"), snapshot)
    and item.attempt_count < 5
)
item.error_summary = "Worker stopped while the external request was in flight; verify receipt before resending."
"""
OLD_PROCESSOR_BLOCK = """
snapshot = delivery.destination_snapshot or {}
retry_deduplicated = (
    delivery_policy.receiver_can_deduplicate(snapshot.get("provider_key"), snapshot)
    and delivery.attempt_count < delivery_policy.MAX_ATTEMPTS
    and (not delivery.expires_at or delivery.expires_at > now)
)
delivery.error_summary = "Webhook worker stopped during an idempotent request; retry scheduled."
"""


@pytest.mark.parametrize("block", [OLD_RECONCILER_BLOCK, OLD_PROCESSOR_BLOCK], ids=["old-reconciler", "old-processor"])
def test_guard_flags_the_old_duplicated_blocks(block):
    found = _find_violations(block, is_policy=False)
    assert "stale summary text" in found
    assert ("attempt_count < number" in found) is (block is OLD_RECONCILER_BLOCK)
    assert not _calls_apply_stale_sending(block)


def test_rule_has_a_single_implementation():
    assert len(GUARDED) > 2
    for path in GUARDED:
        violations = _find_violations(path.read_text(encoding="utf-8"), is_policy=path.name == "delivery_policy.py")
        assert violations == [], (path, violations)
    for path in (RECONCILER, PROCESSOR):
        assert _calls_apply_stale_sending(path.read_text(encoding="utf-8")), path
