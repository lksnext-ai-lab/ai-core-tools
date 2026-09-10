from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scheduling import periodic_agent_task as module


def _db_for(row):
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.one.return_value = row
    db.query.return_value = query
    return db


@pytest.mark.asyncio
async def test_run_scheduled_task_creates_conversation_and_marks_run_succeeded():
    task = SimpleNamespace(
        id=7, agent_id=11, app_id=3, created_by=42, name="Daily", input={"message": "hello"},
        conversation_mode="new_per_run", persistent_conversation_id=None,
    )
    db = _db_for(task)
    conversation = SimpleNamespace(conversation_id=99)
    with (
        patch.object(module, "SessionLocal", return_value=db),
        patch.object(module.ConversationService, "create_conversation", return_value=conversation) as create,
        patch.object(module, "invoke_agent_step", new=AsyncMock(return_value={"ok": True})) as invoke,
    ):
        result = await module._run_scheduled_task(datetime.now(timezone.utc), 7)

    run = db.add.call_args.args[0]
    assert result == {"ok": True}
    assert run.status == "succeeded"
    assert run.conversation_id == 99
    create.assert_called_once()
    invoke.assert_awaited_once_with(11, {"message": "hello"}, 99, 42, 3)
    db.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_scheduled_task_reuses_continuous_conversation_and_records_failure():
    task = SimpleNamespace(
        id=7, agent_id=11, app_id=3, created_by=42, name="Daily", input="raw",
        conversation_mode="continuous", persistent_conversation_id=99,
    )
    db = _db_for(task)
    error = RuntimeError("agent failed")
    with (
        patch.object(module, "SessionLocal", return_value=db),
        patch.object(module.ConversationService, "create_conversation") as create,
        patch.object(module, "invoke_agent_step", new=AsyncMock(side_effect=error)),
    ):
        with pytest.raises(RuntimeError, match="agent failed"):
            await module._run_scheduled_task(datetime.now(timezone.utc), 7)

    run = db.add.call_args.args[0]
    assert run.status == "failed"
    assert run.error_summary == "agent failed"
    create.assert_not_called()


def test_serializable_output_handles_json_and_non_json_results():
    assert module._serializable_output({"ok": True}) == {"ok": True}
    assert module._serializable_output({"bad": object()})["result"].startswith("{")
    assert module._serializable_output("done") == {"result": "done"}


def test_orchestrator_applies_pauses_deletes_and_starts_task(monkeypatch):
    dbos = MagicMock()
    monkeypatch.setattr(module, "DBOS", dbos)
    orchestrator = module.DBOSOrchestrator()
    task = SimpleNamespace(id=7, orchestrator_schedule_name="scheduled-task-7", cron_expression="*/5 * * * *", timezone="UTC")
    handle = SimpleNamespace(workflow_id="wf-1")
    dbos.start_workflow.return_value = handle

    orchestrator.apply_task(task)
    orchestrator.pause_schedule("scheduled-task-7")
    orchestrator.delete_schedule("scheduled-task-7")
    assert orchestrator.run_task_now(task) == "wf-1"
    dbos.apply_schedules.assert_called_once()
    dbos.resume_schedule.assert_called_once_with("scheduled-task-7")
    dbos.start_workflow.assert_called_once()


@pytest.mark.asyncio
async def test_invoke_agent_step_is_explicitly_unavailable_without_dbos(monkeypatch):
    monkeypatch.setattr(module, "DBOS", None)
    with pytest.raises(RuntimeError, match="DBOS is not installed"):
        await module.invoke_agent_step(1, {})
