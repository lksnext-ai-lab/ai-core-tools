from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.scheduled_task_service import ScheduledTaskService


def _db_for(*, agent=None, task=None, runs=None):
    db = MagicMock()
    queries = {}

    def query(model):
        query = queries.setdefault(model, MagicMock())
        query.filter.return_value = query
        query.order_by.return_value = query
        query.offset.return_value = query
        query.limit.return_value = query
        query.one_or_none.return_value = agent if agent is not None and "Agent" in model.__name__ else task
        query.count.return_value = len(runs or [])
        query.all.return_value = runs or []
        return query

    db.query.side_effect = query
    return db, queries


def _task(**overrides):
    values = dict(
        id=7, app_id=3, agent_id=11, created_by=42, name="Daily", input={"message": "hi"},
        cron_expression="*/5 * * * *", timezone="UTC", conversation_mode="new_per_run",
        persistent_conversation_id=None, status="active", max_concurrent_runs=1,
        orchestrator_schedule_name="scheduled-task-7",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_validate_cron_rejects_invalid_expression_and_timezone():
    service = ScheduledTaskService(MagicMock())

    with pytest.raises(ValueError, match="Invalid cron"):
        service.validate_cron("not cron", "UTC")
    with pytest.raises(ValueError, match="Invalid cron"):
        service.validate_cron("*/5 * * * *", "Not/AZone")


def test_validate_cron_rejects_intervals_below_configured_minimum(monkeypatch):
    monkeypatch.setenv("AICT_MIN_SCHEDULE_INTERVAL_SECONDS", "60")
    service = ScheduledTaskService(MagicMock())

    with pytest.raises(ValueError, match="at least 60 seconds"):
        service.validate_cron("*/5 * * * * *", "UTC")


def test_create_validates_agent_and_registers_schedule():
    agent = SimpleNamespace(agent_id=11, app_id=3)
    db, queries = _db_for(agent=agent)
    orchestrator = MagicMock()
    service = ScheduledTaskService(db, orchestrator)
    service.validate_cron = MagicMock()
    db.add.side_effect = lambda task: setattr(task, "id", 7)

    result = service.create(
        app_id=3, created_by=42,
        data={"name": "Daily", "agent_id": 11, "cron_expression": "*/5 * * * *"},
    )

    assert result.name == "Daily"
    assert result.orchestrator_schedule_name == "scheduled-task-7"
    service.validate_cron.assert_called_once_with("*/5 * * * *", "UTC")
    orchestrator.apply_task.assert_called_once_with(result)
    db.commit.assert_called_once()
    assert queries


def test_create_rejects_unknown_agent():
    db, _ = _db_for(agent=None)
    service = ScheduledTaskService(db)

    with pytest.raises(ValueError, match="Agent not found"):
        service.create(app_id=3, created_by=42, data={"name": "x", "agent_id": 99, "cron_expression": "*/5 * * * *"})


def test_list_filters_deleted_tasks_and_optional_agent():
    db, queries = _db_for(runs=["task"])
    service = ScheduledTaskService(db)

    assert service.list(3, agent_id=11) == ["task"]
    query = next(iter(queries.values()))
    assert query.filter.call_count == 2


def test_update_paused_task_pauses_orchestrator_and_ignores_unknown_fields():
    task = _task()
    db, _ = _db_for(task=task)
    orchestrator = MagicMock()
    service = ScheduledTaskService(db, orchestrator)
    service.validate_cron = MagicMock()

    result = service.update(7, 3, {"status": "paused", "name": "Renamed", "agent_id": 999})

    assert result is task
    assert task.name == "Renamed"
    assert task.status == "paused"
    assert not hasattr(task, "agent_id") or task.agent_id == 11
    orchestrator.pause_schedule.assert_called_once_with("scheduled-task-7")
    orchestrator.apply_task.assert_not_called()


def test_delete_marks_task_deleted_and_removes_schedule():
    task = _task()
    db, _ = _db_for(task=task)
    orchestrator = MagicMock()

    ScheduledTaskService(db, orchestrator).delete(7, 3)

    assert task.status == "deleted"
    orchestrator.delete_schedule.assert_called_once_with("scheduled-task-7")
    db.commit.assert_called_once()


def test_runs_paginates_and_run_now_requires_active_task_and_dbos():
    task = _task()
    runs = [SimpleNamespace(id=1)]
    db, _ = _db_for(task=task, runs=runs)
    service = ScheduledTaskService(db)

    items, total = service.runs(7, 3, page=2, per_page=10)
    assert items == runs
    assert total == 1

    with pytest.raises(ValueError, match="DBOS"):
        service.run_now(7, 3)
    task.status = "paused"
    service.orchestrator = MagicMock()
    with pytest.raises(ValueError, match="Only active"):
        service.run_now(7, 3)
