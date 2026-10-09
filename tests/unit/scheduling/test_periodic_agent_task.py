from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scheduling import periodic_agent_task as module


def _db_for(task, run=None):
    db = MagicMock()
    task_query = MagicMock()
    task_query.filter.return_value = task_query
    task_query.one_or_none.return_value = task
    run_query = MagicMock()
    run_query.filter.return_value = run_query
    run_query.one_or_none.return_value = run
    def query(model):
        return run_query if model is module.ScheduledTaskRun else task_query
    db.query.side_effect = query
    return db


def _task(**overrides):
    values = dict(
        id=7, agent_id=11, app_id=3, created_by=42, name="Daily", input={"message": "hello"},
        conversation_mode="new_per_run", persistent_conversation_id=None, max_runs_retained=10,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_run_creates_task_owned_conversation_and_stores_output():
    task = _task()
    db = _db_for(task)
    conversation = SimpleNamespace(conversation_id=99)
    output = {"response": "Informe listo", "files": [{"file_id": "f1", "filename": "a.csv", "file_type": "csv"}]}
    with (
        patch.object(module, "SessionLocal", return_value=db),
        patch.object(module.ConversationService, "create_conversation", return_value=conversation) as create,
        patch.object(module, "invoke_agent_step", new=AsyncMock(return_value=output)) as invoke,
        patch("output.service.create_deliveries_for_run", return_value=[]),
        patch.object(module.ScheduledTaskService, "prune_runs", new=AsyncMock()) as prune,
    ):
        result = await module._run_scheduled_task(datetime.now(timezone.utc), 7)

    run = db.add.call_args.args[0]
    assert result == output
    assert run.status == "succeeded"
    assert run.conversation_id == 99
    assert run.output_text == "Informe listo"
    assert run.output_files == output["files"]
    kwargs = create.call_args.kwargs
    assert kwargs["scheduled_task_id"] == 7
    assert kwargs["user_context"]["user_id"] == "scheduled_task_7"  # not the creator
    context = invoke.await_args.args[3]
    assert context["scheduled_task_id"] == 7
    assert context["billing_user_id"] == 42
    assert context["caller_type_override"] == "SCHEDULED_TASK"
    assert invoke.await_args.args[:3] == (11, {"message": "hello"}, 99)
    prune.assert_awaited_once()
    db.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_reuses_continuous_conversation_and_records_failure():
    task = _task(input="raw", conversation_mode="continuous", persistent_conversation_id=99)
    db = _db_for(task)
    error = RuntimeError("agent failed")
    with (
        patch.object(module, "SessionLocal", return_value=db),
        patch.object(module.ConversationService, "create_conversation") as create,
        patch.object(module, "invoke_agent_step", new=AsyncMock(side_effect=error)),
        patch.object(module.ScheduledTaskService, "prune_runs", new=AsyncMock()),
    ):
        with pytest.raises(RuntimeError, match="agent failed"):
            await module._run_scheduled_task(datetime.now(timezone.utc), 7)

    run = db.add.call_args.args[0]
    assert run.status == "failed"
    assert run.error_summary == "agent failed"
    assert run.conversation_id == 99
    create.assert_not_called()


@pytest.mark.asyncio
async def test_run_of_a_deleted_task_is_skipped():
    db = _db_for(None)
    with (
        patch.object(module, "SessionLocal", return_value=db),
        patch.object(module, "invoke_agent_step", new=AsyncMock()) as invoke,
    ):
        assert await module._run_scheduled_task(datetime.now(timezone.utc), 7) is None
    invoke.assert_not_awaited()
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_invoke_agent_keeps_only_text_and_files():
    service = MagicMock()
    service.execute_agent_chat_with_file_refs = AsyncMock(return_value={
        "response": {"summary": "ok"},
        "files_data": [{"file_id": "f1", "filename": "chart.png", "file_type": "image"}],
        "metadata": {"agent_name": "x"},
    })
    with (
        patch.object(module, "SessionLocal", return_value=MagicMock()),
        patch("services.agent_execution_service.AgentExecutionService", return_value=service),
    ):
        result = await module._invoke_agent(11, {"message": "hi"}, 99, {"user_id": "scheduled_task_7"})

    assert result == {
        "response": '{"summary": "ok"}',
        "files": [{"file_id": "f1", "filename": "chart.png", "file_type": "image"}],
    }


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


def test_system_database_url_prefers_dbos_database_url(monkeypatch):
    monkeypatch.setenv("DBOS_DATABASE_URL", "postgresql://dbos@db/dbos")
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "postgresql://app@db/app")

    assert module._system_database_url() == "postgresql://dbos@db/dbos"


def test_system_database_url_defaults_to_application_database(monkeypatch):
    monkeypatch.delenv("DBOS_DATABASE_URL", raising=False)
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "postgresql://app@db/app")

    assert module._system_database_url() == "postgresql://app@db/app"


@pytest.mark.parametrize("value, expected", [
    (None, True), ("true", True), ("1", True), ("false", False), ("FALSE", False), ("0", False), ("off", False),
])
def test_dbos_enabled_flag(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("DBOS_ENABLED", raising=False)
    else:
        monkeypatch.setenv("DBOS_ENABLED", value)
    assert module.dbos_enabled() is expected


@pytest.mark.asyncio
async def test_initialize_dbos_does_nothing_when_disabled(monkeypatch):
    monkeypatch.setenv("DBOS_ENABLED", "false")
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "postgresql://app@db/app")
    with patch.object(module, "DBOS") as dbos:
        assert await module.initialize_dbos() is False
        dbos.launch.assert_not_called()
    assert module.dbos_running() is False
