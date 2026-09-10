"""The only backend module that imports DBOS directly."""

import json
import os
from datetime import datetime, timezone
from typing import Any

from db.database import SessionLocal
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from models.conversation import ConversationSource
from services.conversation_service import ConversationService

try:
    from dbos import DBOS, DBOSConfig
except ImportError:  # Keeps unit tests and local tooling usable before dependencies are installed.
    DBOS = None
    DBOSConfig = dict


if DBOS is not None:
    @DBOS.step(retries_allowed=True, max_attempts=3, interval_seconds=5, backoff_rate=2.0)
    async def invoke_agent_step(
        agent_id: int,
        input_context: dict[str, Any] | None,
        conversation_id: int | None = None,
        user_id: int | None = None,
        app_id: int | None = None,
    ):
        from services.agent_execution_service import AgentExecutionService

        context = input_context or {}
        message = context.get("message") or json.dumps(context, ensure_ascii=False, default=str)
        db = SessionLocal()
        try:
            return await AgentExecutionService().execute_agent_chat_with_file_refs(
                agent_id=agent_id,
                message=message,
                user_context={"trigger": "scheduled_task", "user_id": user_id, "app_id": app_id},
                conversation_id=conversation_id,
                db=db,
            )
        finally:
            db.close()

    @DBOS.workflow(max_recovery_attempts=3)
    async def periodic_task_run(scheduled_time: datetime, task_id: int):
        return await _run_scheduled_task(scheduled_time, task_id)
else:
    async def invoke_agent_step(
        agent_id: int,
        input_context: dict[str, Any] | None,
        conversation_id: int | None = None,
        user_id: int | None = None,
        app_id: int | None = None,
    ):
        raise RuntimeError("DBOS is not installed")

    async def periodic_task_run(scheduled_time: datetime, task_id: int):
        return await _run_scheduled_task(scheduled_time, task_id)


async def _run_scheduled_task(scheduled_time: datetime, task_id: int):
    db = SessionLocal()
    run = None
    try:
        task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).one()
        if task.conversation_mode == "continuous" and task.persistent_conversation_id:
            conversation_id = task.persistent_conversation_id
        else:
            conversation = ConversationService.create_conversation(
                db=db,
                agent_id=task.agent_id,
                user_context={"user_id": task.created_by, "app_id": task.app_id},
                title=task.name,
                source=ConversationSource.SCHEDULED_TASK,
            )
            conversation_id = conversation.conversation_id
            if task.conversation_mode == "continuous":
                task.persistent_conversation_id = conversation_id
                db.commit()
        run_id = getattr(DBOS, "workflow_id", None) or f"task-{task_id}-{scheduled_time.isoformat()}"
        run = ScheduledTaskRun(
            scheduled_task_id=task.id, conversation_id=conversation_id,
            orchestrator_run_id=str(run_id), scheduled_time=scheduled_time,
            started_at=datetime.now(timezone.utc), status="running", attempt_count=1,
        )
        db.add(run)
        db.commit()
        context = task.input if isinstance(task.input, dict) else {"input": task.input}
        result = await invoke_agent_step(task.agent_id, context, conversation_id, task.created_by, task.app_id)
        run.status = "succeeded"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return result
    except Exception as exc:
        if run is not None:
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.error_summary = str(exc)[:4000]
            db.commit()
        raise
    finally:
        db.close()


class DBOSOrchestrator:
    """Small synchronous adapter used by ScheduledTaskService."""

    def apply_task(self, task: ScheduledTask) -> None:
        DBOS.apply_schedules([{
            "schedule_name": task.orchestrator_schedule_name,
            "workflow_fn": periodic_task_run,
            "schedule": task.cron_expression,
            "cron_timezone": task.timezone,
            "context": task.id,
            "queue_name": "periodic-agents",
        }])
        DBOS.resume_schedule(task.orchestrator_schedule_name)

    def pause_schedule(self, schedule_name: str) -> None:
        DBOS.pause_schedule(schedule_name)

    def delete_schedule(self, schedule_name: str) -> None:
        DBOS.delete_schedule(schedule_name)

    def run_task_now(self, task: ScheduledTask) -> str:
        """Queue one ad-hoc execution through the same durable workflow as the schedule."""
        handle = DBOS.start_workflow(periodic_task_run, datetime.now(timezone.utc), task.id)
        workflow_id = getattr(handle, "get_workflow_id", None)
        return str(workflow_id() if callable(workflow_id) else getattr(handle, "workflow_id", handle))


async def initialize_dbos() -> bool:
    """Initialize DBOS once when a system database is configured."""
    if DBOS is None or not os.getenv("DBOS_DATABASE_URL"):
        return False
    if getattr(initialize_dbos, "started", False):
        return True
    config: DBOSConfig = {
        "name": os.getenv("DBOS_APPLICATION_NAME", "mattin-ai"),
        "application_version": os.getenv("APP_VERSION", "0.2.37"),
        "system_database_url": os.environ["DBOS_DATABASE_URL"],
    }
    DBOS(config=config)
    DBOS.launch()
    await DBOS.register_queue_async(
        "periodic-agents",
        global_concurrency=int(os.getenv("AICT_SCHEDULE_CONCURRENCY", "10")),
    )
    # Reconcile application-active schedules with DBOS after a restart. DBOS
    # persists a paused state, while the application row can still be active.
    db = SessionLocal()
    try:
        orchestrator = DBOSOrchestrator()
        for task in db.query(ScheduledTask).filter(ScheduledTask.status == "active").all():
            orchestrator.apply_task(task)
    finally:
        db.close()
    initialize_dbos.started = True
    return True


def shutdown_dbos() -> None:
    if DBOS is not None and getattr(initialize_dbos, "started", False):
        DBOS.destroy()
        initialize_dbos.started = False


def _serializable_output(result: Any) -> dict[str, Any]:
    """Keep the user-facing mirror small and JSON serializable."""
    if isinstance(result, dict):
        try:
            json.dumps(result)
            return result
        except (TypeError, ValueError):
            pass
    return {"result": str(result)[:4000]}
