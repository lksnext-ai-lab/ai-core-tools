from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.agent_scheduler_service import AgentSchedulerService


def _db(agent=None, schedule=None):
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.one_or_none.return_value = agent if agent is not None else schedule
    query.all.return_value = [schedule] if schedule else []
    query.count.return_value = 1
    db.query.return_value = query
    return db, query


def test_schedule_name_and_cron_minimum():
    assert AgentSchedulerService.schedule_name(12) == "agent-schedule-12"
    with pytest.raises(ValueError, match="at least 60 seconds"):
        AgentSchedulerService.validate_cron("*/5 * * * * *", "UTC")


def test_create_schedule_persists_and_applies_schedule(monkeypatch):
    monkeypatch.setenv("AICT_MIN_SCHEDULE_INTERVAL_SECONDS", "60")
    db, _ = _db(agent=SimpleNamespace(agent_id=4, app_id=2))
    db.add.side_effect = lambda schedule: setattr(schedule, "id", 12)
    orchestrator = MagicMock()
    service = AgentSchedulerService(db, orchestrator)
    service.validate_cron = MagicMock()

    schedule = service.create_schedule(
        agent_id=4, app_id=2, created_by=8, cron_expression="*/5 * * * *",
    )

    assert schedule.orchestrator_schedule_name == "agent-schedule-12"
    service.validate_cron.assert_called_once()
    orchestrator.apply_schedule.assert_called_once_with(schedule)
    db.commit.assert_called_once()


def test_delete_schedule_deletes_orchestrator_and_marks_row():
    schedule = SimpleNamespace(id=12, agent_id=4, app_id=2, orchestrator_schedule_name="agent-schedule-12", status="active")
    db, _ = _db(schedule=schedule)
    orchestrator = MagicMock()

    AgentSchedulerService(db, orchestrator).delete_schedule(12, 4, 2)

    assert schedule.status == "deleted"
    orchestrator.delete_schedule.assert_called_once_with("agent-schedule-12")
