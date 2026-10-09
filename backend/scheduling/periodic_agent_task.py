"""The only backend module that imports DBOS directly."""

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from db.database import SessionLocal
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from models.conversation import ConversationSource
from services.conversation_service import ConversationService
from services.scheduled_task_service import ScheduledTaskService, task_user_context
from utils.logger import get_logger

logger = get_logger(__name__)

try:
    from dbos import DBOS, DBOSConfig
except ImportError:  # Keeps unit tests and local tooling usable before dependencies are installed.
    DBOS = None
    DBOSConfig = dict


async def _invoke_agent(
    agent_id: int,
    input_context: dict[str, Any] | None,
    conversation_id: int | None,
    user_context: dict[str, Any],
) -> dict[str, Any]:
    """Run the agent once and return only what the run keeps: its answer and produced files."""
    from fastapi import HTTPException
    from models.hitl_approval import ApprovalChannel
    from services.agent_execution_service import AgentExecutionService
    from services.hitl_approval_service import ApprovalNotSupportedError

    context = input_context or {}
    message = context.get("message") or json.dumps(context, ensure_ascii=False, default=str)
    db = SessionLocal()
    try:
        result = await AgentExecutionService().execute_agent_chat_with_file_refs(
            agent_id=agent_id,
            message=message,
            user_context=dict(user_context),
            conversation_id=conversation_id,
            db=db,
            channel=ApprovalChannel.SCHEDULED,
        )
    except HTTPException as exc:
        # Nobody can approve a tool during a scheduled run; the pause was already
        # rejected, so record why instead of retrying a run that would pause again.
        if isinstance(exc.detail, dict) and exc.detail.get("code") == ApprovalNotSupportedError.code:
            return {"response": exc.detail["message"], "files": []}
        raise
    finally:
        db.close()
    return {
        "response": _response_text(result.get("response")),
        "files": [
            {"file_id": f["file_id"], "filename": f["filename"], "file_type": f.get("file_type")}
            for f in result.get("files_data") or []
        ],
    }


if DBOS is not None:
    @DBOS.step(retries_allowed=True, max_attempts=3, interval_seconds=5, backoff_rate=2.0)
    async def invoke_agent_step(
        agent_id: int,
        input_context: dict[str, Any] | None,
        conversation_id: int | None = None,
        user_context: dict[str, Any] | None = None,
    ):
        # Check at call time as well as import time. Tests and applications may
        # unload/disable DBOS after this function has been defined, and the
        # decorated implementation must not touch the application database in
        # that state.
        if DBOS is None:
            raise RuntimeError("DBOS is not installed")
        return await _invoke_agent(agent_id, input_context, conversation_id, user_context or {})

    @DBOS.workflow(max_recovery_attempts=3)
    async def periodic_task_run(scheduled_time: datetime, task_id: int):
        return await _run_scheduled_task(scheduled_time, task_id)
else:
    async def invoke_agent_step(
        agent_id: int,
        input_context: dict[str, Any] | None,
        conversation_id: int | None = None,
        user_context: dict[str, Any] | None = None,
    ):
        raise RuntimeError("DBOS is not installed")

    async def periodic_task_run(scheduled_time: datetime, task_id: int):
        return await _run_scheduled_task(scheduled_time, task_id)


def _response_text(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    return json.dumps(response, ensure_ascii=False, default=str)


def _conversation_for_run(db, task: ScheduledTask, scheduled_time: datetime) -> int:
    """The conversation this run writes to. It belongs to the task, never to a user."""
    if task.conversation_mode == "continuous" and task.persistent_conversation_id:
        return task.persistent_conversation_id
    title = task.name if task.conversation_mode == "continuous" else f"{task.name} · {scheduled_time:%Y-%m-%d %H:%M}"
    conversation = ConversationService.create_conversation(
        db=db,
        agent_id=task.agent_id,
        user_context=task_user_context(task),
        title=title[:255],
        source=ConversationSource.SCHEDULED_TASK,
        scheduled_task_id=task.id,
    )
    if task.conversation_mode == "continuous":
        task.persistent_conversation_id = conversation.conversation_id
        db.commit()
    return conversation.conversation_id


async def _run_scheduled_task(scheduled_time: datetime, task_id: int):
    db = SessionLocal()
    run = None
    try:
        task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).one_or_none()
        if task is None:
            logger.info("Scheduled task %s no longer exists; skipping run", task_id)
            return None
        conversation_id = _conversation_for_run(db, task, scheduled_time)
        run_id = getattr(DBOS, "workflow_id", None) or f"task-{task_id}-{scheduled_time.isoformat()}"
        run = ScheduledTaskRun(
            scheduled_task_id=task.id, conversation_id=conversation_id,
            orchestrator_run_id=str(run_id), scheduled_time=scheduled_time,
            started_at=datetime.now(timezone.utc), status="running", attempt_count=1,
        )
        db.add(run)
        db.commit()
        context = task.input if isinstance(task.input, dict) else {"input": task.input}
        result = await invoke_agent_step(task.agent_id, context, conversation_id, task_user_context(task))
        run.status = "succeeded"
        run.finished_at = datetime.now(timezone.utc)
        run.output_text = (result or {}).get("response")
        run.output_files = (result or {}).get("files") or []
        db.commit()
        await _prune(db, task)
        return result
    except Exception as exc:
        db.rollback()
        if run is not None:
            try:
                run.status = "failed"
                run.finished_at = datetime.now(timezone.utc)
                run.error_summary = str(getattr(exc, "detail", None) or exc)[:4000]
                db.commit()
                await _prune(db, run.task)
            except Exception:  # The task may have been deleted mid-run.
                db.rollback()
                logger.warning("Could not record failure of scheduled task %s run", task_id, exc_info=True)
        raise
    finally:
        db.close()


async def _prune(db, task: ScheduledTask) -> None:
    try:
        await ScheduledTaskService(db).prune_runs(task)
    except Exception:
        db.rollback()
        logger.warning("Could not prune old runs of scheduled task %s", task.id, exc_info=True)


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


def _system_database_url() -> Optional[str]:
    """DBOS_DATABASE_URL, or the application database (DBOS keeps its tables in the "dbos" schema)."""
    return os.getenv("DBOS_DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")


def dbos_enabled() -> bool:
    """DBOS_ENABLED=false turns scheduling off (e.g. tests); on by default."""
    return os.getenv("DBOS_ENABLED", "true").strip().lower() not in ("false", "0", "no", "off")


def dbos_running() -> bool:
    """True once initialize_dbos() has launched DBOS in this process."""
    return bool(getattr(initialize_dbos, "started", False))


async def initialize_dbos() -> bool:
    """Initialize DBOS once when enabled and a system database is available."""
    system_database_url = _system_database_url()
    if DBOS is None or not system_database_url or not dbos_enabled():
        return False
    if getattr(initialize_dbos, "started", False):
        return True
    config: DBOSConfig = {
        "name": os.getenv("DBOS_APPLICATION_NAME", "mattin-ai"),
        "application_version": os.getenv("APP_VERSION", "0.2.37"),
        "system_database_url": system_database_url,
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
