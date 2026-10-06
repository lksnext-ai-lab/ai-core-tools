from types import SimpleNamespace
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

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


def test_list_filters_by_app_and_optional_agent():
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


@pytest.mark.asyncio
async def test_delete_removes_schedule_conversations_files_and_history():
    task = _task(persistent_conversation_id=5)
    conversation = SimpleNamespace(conversation_id=5, agent_id=11, session_id="conv_11_abc")
    db, queries = _db_for(task=task)
    db.query.side_effect = None
    query = MagicMock()
    query.filter.return_value = query
    query.one_or_none.return_value = task
    query.all.return_value = [conversation]
    db.query.return_value = query
    orchestrator = MagicMock()

    with (
        patch("services.conversation_service.ConversationService.release_conversation_resources") as release,
        patch("services.conversation_service.ConversationService.delete_thread_history", new=AsyncMock()) as history,
        patch("services.file_management_service.FileManagementService") as files,
    ):
        await ScheduledTaskService(db, orchestrator).delete(7, 3)

    orchestrator.delete_schedule.assert_called_once_with("scheduled-task-7")
    release.assert_called_once_with(db, conversation)
    storage_args = files.return_value.delete_conversation_storage.call_args.args
    assert storage_args[0] == 11 and storage_args[2] == "5"
    assert storage_args[1]["user_id"] == "scheduled_task_7"
    db.delete.assert_any_call(conversation)
    db.delete.assert_any_call(task)
    history.assert_awaited_once_with(11, "conv_11_abc")
    assert task.persistent_conversation_id is None


def _prune_db(runs, conversations):
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = runs
    db.query.return_value = query
    db.get.side_effect = lambda model, conversation_id: conversations.get(conversation_id)
    return db


@pytest.mark.asyncio
async def test_prune_keeps_newest_runs_and_drops_old_conversations():
    task = _task(max_runs_retained=2)
    runs = [SimpleNamespace(id=i, conversation_id=100 + i, output_files=[]) for i in (4, 3, 2, 1)]
    conversations = {c: SimpleNamespace(conversation_id=c, agent_id=11, session_id=f"s{c}") for c in (101, 102, 103, 104)}
    db = _prune_db(runs, conversations)

    with (
        patch("services.conversation_service.ConversationService.release_conversation_resources") as release,
        patch("services.conversation_service.ConversationService.delete_thread_history", new=AsyncMock()) as history,
        patch("services.file_management_service.FileManagementService"),
    ):
        pruned = await ScheduledTaskService(db).prune_runs(task)

    assert pruned == 2
    assert [c.args[1].conversation_id for c in release.call_args_list] == [102, 101]
    db.delete.assert_any_call(runs[2])
    db.delete.assert_any_call(runs[3])
    assert history.await_count == 2


@pytest.mark.asyncio
async def test_prune_in_continuous_mode_keeps_conversation_and_removes_run_files():
    task = _task(max_runs_retained=1, conversation_mode="continuous", persistent_conversation_id=50)
    runs = [
        SimpleNamespace(id=2, conversation_id=50, output_files=[]),
        SimpleNamespace(id=1, conversation_id=50, output_files=[{"file_id": "f1", "filename": "a.png"}]),
    ]
    conversation = SimpleNamespace(conversation_id=50, agent_id=11, session_id="s50")
    db = _prune_db(runs, {50: conversation})

    with (
        patch("services.conversation_service.ConversationService.release_conversation_resources") as release,
        patch("services.file_management_service.FileManagementService") as files,
    ):
        files.return_value.remove_files = AsyncMock()
        assert await ScheduledTaskService(db).prune_runs(task) == 1

    release.assert_not_called()
    files.return_value.remove_files.assert_awaited_once()
    assert files.return_value.remove_files.await_args.args[0] == ["f1"]
    db.delete.assert_called_once_with(runs[1])


@pytest.mark.asyncio
async def test_prune_is_a_noop_within_the_limit():
    db = _prune_db([SimpleNamespace(id=1, conversation_id=1, output_files=[])], {})
    assert await ScheduledTaskService(db).prune_runs(_task(max_runs_retained=10)) == 0
    db.commit.assert_not_called()


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


def test_create_rejects_continuous_mode_for_agents_without_memory():
    db, _ = _db_for(agent=SimpleNamespace(agent_id=11, app_id=3, has_memory=False))
    service = ScheduledTaskService(db)
    with pytest.raises(ValueError, match="memory"):
        service.create(app_id=3, created_by=42, data={
            "name": "x", "agent_id": 11, "cron_expression": "*/5 * * * *", "conversation_mode": "continuous",
        })


@pytest.mark.asyncio
async def test_prune_preserves_runs_with_nonterminal_output_deliveries():
    task = _task(max_runs_retained=1)
    protected = SimpleNamespace(
        id=1, conversation_id=101, output_files=[],
        output_deliveries=[SimpleNamespace(status="pending")],
    )
    newest = SimpleNamespace(id=2, conversation_id=102, output_files=[], output_deliveries=[])
    db = _prune_db([newest, protected], {})

    assert await ScheduledTaskService(db).prune_runs(task) == 0
    db.delete.assert_not_called()


@pytest.mark.parametrize("status", ["accepted", "failed"])
@pytest.mark.asyncio
async def test_prune_preserves_notification_links_until_delivery_expiry(status):
    protected = SimpleNamespace(
        id=1, conversation_id=None, output_files=[],
        output_deliveries=[SimpleNamespace(status=status, expires_at=datetime.utcnow() + timedelta(hours=1))],
    )
    newest = SimpleNamespace(id=2, conversation_id=None, output_files=[], output_deliveries=[])
    db = _prune_db([newest, protected], {})

    assert await ScheduledTaskService(db).prune_runs(_task(max_runs_retained=1)) == 0
    db.delete.assert_not_called()


@pytest.mark.asyncio
async def test_prune_releases_notification_run_after_expiry():
    expired = SimpleNamespace(
        id=1, conversation_id=None, output_files=[],
        output_deliveries=[SimpleNamespace(status="accepted", expires_at=datetime.utcnow() - timedelta(seconds=1))],
    )
    newest = SimpleNamespace(id=2, conversation_id=None, output_files=[], output_deliveries=[])
    db = _prune_db([newest, expired], {})

    assert await ScheduledTaskService(db).prune_runs(_task(max_runs_retained=1)) == 1
    db.delete.assert_called_once_with(expired)
