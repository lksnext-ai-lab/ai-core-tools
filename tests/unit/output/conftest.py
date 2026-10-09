"""Shared fixtures for the scheduled-task output outbox tests.

An isolated in-memory SQLite database holds only the outbox tables (foreign
keys to unrelated application entities are not enforced by SQLite), the
spool root is redirected to ``tmp_path`` and DNS resolution is stubbed to a
public address so destination validation never touches the network.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import database
from models.output_delivery import OutputArtifact, OutputDelivery, OutputDeliveryAttempt, OutputDestination, ScheduledTaskOutputBinding
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from output import teams_workflow


@pytest.fixture
def outbox(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    database.Base.metadata.create_all(engine, tables=[model.__table__ for model in (
        ScheduledTask, ScheduledTaskRun, OutputDestination, ScheduledTaskOutputBinding,
        OutputDelivery, OutputDeliveryAttempt, OutputArtifact,
    )])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    spool = tmp_path / "output-deliveries"
    spool.mkdir()
    monkeypatch.setattr("output.service._spool_root", lambda: spool)
    monkeypatch.setattr(teams_workflow, "resolve_host", lambda host: ["20.1.2.3"])
    monkeypatch.setenv("FRONTEND_URL", "https://mattin.example")
    factory.spool = spool
    yield factory
    engine.dispose()

