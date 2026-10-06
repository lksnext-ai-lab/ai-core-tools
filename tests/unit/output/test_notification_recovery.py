"""Notification recovery and file retention against an isolated SQLite database."""

import json
import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db import database
from models.output_delivery import OutputDelivery, OutputDeliveryAttempt, OutputDestination, ScheduledTaskOutputBinding
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from scheduling import output_delivery
from services import file_cleanup_worker


@pytest.fixture
def sessions(monkeypatch):
    engine = create_engine("sqlite://")
    # Foreign keys to unrelated application entities are not enforced by SQLite.
    # Use the production outbox models and real SQL transactions/savepoints.
    tables = [model.__table__ for model in (
        ScheduledTask, ScheduledTaskRun, OutputDestination, ScheduledTaskOutputBinding,
        OutputDelivery, OutputDeliveryAttempt,
    )]
    database.Base.metadata.create_all(engine, tables=tables)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(output_delivery, "SessionLocal", factory)
    with factory() as db:
        db.add(ScheduledTask(id=1, name="Daily", app_id=1, agent_id=1, created_by=1,
                             cron_expression="0 8 * * *", orchestrator_schedule_name="task-1"))
        db.add(OutputDestination(id=1, app_id=1, name="Teams", webhook_url="secret"))
        db.add(ScheduledTaskOutputBinding(id=1, scheduled_task_id=1, destination_id=1))
        db.commit()
    yield factory
    engine.dispose()


def _run(run_id, *, reconciled=True, files=None):
    return ScheduledTaskRun(id=run_id, scheduled_task_id=1, status="succeeded",
                            scheduled_time=datetime.utcnow(), orchestrator_run_id=f"run-{run_id}",
                            output_text="Result", output_files=files or [], outputs_reconciled=reconciled)


def _delivery(run_id, *, status="pending", expires_at=None):
    return OutputDelivery(run_id=run_id, binding_id=1, destination_id=1,
                          status=status, expires_at=expires_at)


def _old_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(file_cleanup_worker, "_config", lambda: {
        "TMP_BASE_FOLDER": str(tmp_path), "TMP_CLEANUP_ENABLED": True,
        "TMP_EPHEMERAL_ORPHAN_HOURS": 1, "TMP_PERSISTENT_TTL_DAYS": 7,
    })
    metadata = tmp_path / "persistent" / "session" / "file-1.json"
    metadata.parent.mkdir(parents=True)
    content = metadata.with_suffix(".content")
    backing = tmp_path / "uploads" / "report.csv"
    backing.parent.mkdir()
    unrelated = backing.parent / "unrelated.csv"
    metadata.write_text(json.dumps({"file_id": "file-1", "file_path": "uploads/report.csv"}))
    for path in (content, backing, unrelated):
        path.write_text("result")
    old = (datetime.utcnow() - timedelta(days=9)).timestamp()
    for path in (metadata, content, backing, unrelated):
        os.utime(path, (old, old))
    return metadata, content, backing, unrelated


@pytest.mark.parametrize("status", ["pending", "sending", "retry_wait", "unknown", "failed", "accepted"])
def test_cleanup_preserves_notification_metadata_and_bytes_until_expiry(sessions, tmp_path, monkeypatch, status):
    paths = _old_artifacts(tmp_path, monkeypatch)
    with sessions() as db:
        db.add(_run(1, files=[{"file_id": "file-1"}]))
        db.add(_delivery(1, status=status, expires_at=datetime.utcnow() + timedelta(hours=1)))
        db.commit()

    file_cleanup_worker._run_one_sweep_sync()

    assert all(path.exists() for path in paths[:3])
    assert not paths[3].exists()


@pytest.mark.parametrize("status,expired", [("pending", True), ("cancelled", False)])
def test_cleanup_releases_expired_or_cancelled_notification_files(sessions, tmp_path, monkeypatch, status, expired):
    paths = _old_artifacts(tmp_path, monkeypatch)
    with sessions() as db:
        db.add(_run(1, files=[{"file_id": "file-1"}]))
        db.add(_delivery(1, status=status, expires_at=datetime.utcnow() + timedelta(hours=-1 if expired else 1)))
        db.commit()

    file_cleanup_worker._run_one_sweep_sync()

    assert all(not path.exists() for path in paths)


def test_cleanup_skips_deletion_when_notification_protection_cannot_be_loaded(tmp_path, monkeypatch):
    paths = _old_artifacts(tmp_path, monkeypatch)
    def unavailable():
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(database, "SessionLocal", unavailable)

    file_cleanup_worker._run_one_sweep_sync()

    assert all(path.exists() for path in paths)


def test_cleanup_skips_deletion_when_protected_metadata_is_unreadable(sessions, tmp_path, monkeypatch):
    paths = _old_artifacts(tmp_path, monkeypatch)
    paths[0].write_text("invalid JSON")
    with sessions() as db:
        db.add(_run(1, files=[{"file_id": "file-1"}]))
        db.add(_delivery(1, expires_at=datetime.utcnow() + timedelta(hours=1)))
        db.commit()

    file_cleanup_worker._run_one_sweep_sync()

    assert all(path.exists() for path in paths)


@pytest.mark.parametrize("database_error", [False, True])
@pytest.mark.asyncio
async def test_failed_outbox_repair_does_not_block_other_runs_or_pending_deliveries(sessions, monkeypatch, database_error):
    with sessions() as db:
        db.add_all([_run(1, reconciled=False), _run(2, reconciled=False), _run(3)])
        db.add(_delivery(3, expires_at=datetime.utcnow() + timedelta(days=1)))
        db.commit()

    create = output_delivery.create_deliveries_for_run
    def repair(db, *, task, run):
        deliveries = create(db, task=task, run=run)
        if run.id == 1:
            if database_error:
                db.add(_delivery(1))  # Violates the outbox's uniqueness constraint.
                db.flush()
            raise ValueError("result could not be rendered")
        return deliveries
    monkeypatch.setattr(output_delivery, "create_deliveries_for_run", repair)
    queued = []
    monkeypatch.setattr(output_delivery, "enqueue_delivery", lambda delivery_id, generation: queued.append((delivery_id, generation)))

    assert await output_delivery._reconcile_pending_deliveries() == 2

    with sessions() as db:
        assert db.get(ScheduledTaskRun, 1).outputs_reconciled is False
        assert not db.query(OutputDelivery).filter_by(run_id=1).all()
        assert db.get(ScheduledTaskRun, 2).outputs_reconciled is True
        assert {db.get(OutputDelivery, delivery_id).run_id for delivery_id, _ in queued} == {2, 3}
