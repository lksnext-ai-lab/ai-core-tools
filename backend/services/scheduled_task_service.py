"""Application service for first-class scheduled tasks."""

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from sqlalchemy.orm import Session

from models.agent import Agent, MarketplaceVisibility
from models.conversation import Conversation
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from models.output_delivery import OutputDelivery
from utils.logger import get_logger

logger = get_logger(__name__)

_EDITABLE_FIELDS = {
    "name", "description", "input", "cron_expression", "timezone", "max_concurrent_runs",
    "status", "max_runs_retained", "marketplace_visibility",
}
_FINISHED_STATUSES = ("succeeded", "failed")
# Background history deletions started from sync code (agent/app deletion).
_pending_cleanups: set = set()


def task_user_context(task: ScheduledTask) -> Dict[str, Any]:
    """Identity a scheduled task runs its agent with.

    Its conversations belong to the task (no user), files are scoped by the task's own
    session key, system-LLM usage is billed to the creator and metrics report the
    SCHEDULED_TASK channel.
    """
    return {
        "user_id": f"scheduled_task_{task.id}",
        "app_id": task.app_id,
        "scheduled_task_id": task.id,
        "billing_user_id": task.created_by,
        "caller_type_override": "SCHEDULED_TASK",
        "trigger": "scheduled_task",
    }


def default_orchestrator():
    """The DBOS orchestrator once DBOS has launched in this process, else None."""
    from scheduling.periodic_agent_task import DBOSOrchestrator, dbos_running
    return DBOSOrchestrator() if dbos_running() else None


class ScheduledTaskService:
    def __init__(self, db: Session, orchestrator=None):
        self.db = db
        self.orchestrator = orchestrator
        self.minimum_interval_seconds = int(os.getenv("AICT_MIN_SCHEDULE_INTERVAL_SECONDS", "60"))

    def validate_cron(self, expression: str, timezone_name: str) -> None:
        try:
            base = datetime.now(ZoneInfo(timezone_name))
            iterator = croniter(expression, base)
            first = iterator.get_next(datetime)
            second = iterator.get_next(datetime)
        except (ValueError, TypeError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Invalid cron expression or timezone") from exc
        if (second - first).total_seconds() < self.minimum_interval_seconds:
            raise ValueError(f"Schedule interval must be at least {self.minimum_interval_seconds} seconds")

    def _agent(self, agent_id: int, app_id: int) -> Agent:
        agent = self.db.query(Agent).filter(Agent.agent_id == agent_id, Agent.app_id == app_id).one_or_none()
        if not agent:
            raise ValueError("Agent not found")
        return agent

    def _task(self, task_id: int, app_id: Optional[int] = None) -> ScheduledTask:
        query = self.db.query(ScheduledTask).filter(ScheduledTask.id == task_id)
        if app_id is not None:
            query = query.filter(ScheduledTask.app_id == app_id)
        task = query.one_or_none()
        if not task:
            raise ValueError("Scheduled task not found")
        return task

    def get(self, task_id: int, app_id: int) -> ScheduledTask:
        return self._task(task_id, app_id)

    def create(self, *, app_id: int, created_by: int, data: Dict[str, Any]) -> ScheduledTask:
        agent = self._agent(data["agent_id"], app_id)
        if data.get("conversation_mode") == "continuous" and not getattr(agent, "has_memory", False):
            # Without memory every run would start from scratch: not a continuous conversation.
            raise ValueError("Continuous conversations require an agent with memory enabled")
        self.validate_cron(data["cron_expression"], data.get("timezone", "UTC"))
        task = ScheduledTask(
            app_id=app_id, created_by=created_by, name=data["name"], agent_id=data["agent_id"],
            description=data.get("description"),
            input=data.get("input", {}), cron_expression=data["cron_expression"],
            timezone=data.get("timezone", "UTC"), conversation_mode=data.get("conversation_mode", "new_per_run"),
            max_concurrent_runs=data.get("max_concurrent_runs", 1),
            max_runs_retained=data.get("max_runs_retained") or 10,
            marketplace_visibility=_visibility(data.get("marketplace_visibility")),
            orchestrator_schedule_name="pending",
        )
        self.db.add(task)
        self.db.flush()
        task.orchestrator_schedule_name = f"scheduled-task-{task.id}"
        self._apply(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def list(self, app_id: int, agent_id: Optional[int] = None):
        query = self.db.query(ScheduledTask).filter(ScheduledTask.app_id == app_id)
        if agent_id is not None:
            query = query.filter(ScheduledTask.agent_id == agent_id)
        return query.order_by(ScheduledTask.created_at.desc()).all()

    def update(self, task_id: int, app_id: int, changes: Dict[str, Any]) -> ScheduledTask:
        task = self._task(task_id, app_id)
        cron = changes.get("cron_expression") or task.cron_expression
        timezone = changes.get("timezone") or task.timezone
        self.validate_cron(cron, timezone)
        for key, value in changes.items():
            if key not in _EDITABLE_FIELDS:
                continue
            if key == "description":
                task.description = value
            elif value is not None:
                setattr(task, key, _visibility(value) if key == "marketplace_visibility" else value)
        if task.status == "paused":
            self._pause(task)
        else:
            self._apply(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def runs(self, task_id: int, app_id: int, page: int, per_page: int):
        task = self._task(task_id, app_id)
        return self.runs_of(task, page, per_page)

    def runs_of(self, task: ScheduledTask, page: int, per_page: int):
        query = self.db.query(ScheduledTaskRun).filter(ScheduledTaskRun.scheduled_task_id == task.id)
        total = query.count()
        items = (
            query.order_by(ScheduledTaskRun.scheduled_time.desc(), ScheduledTaskRun.id.desc())
            .offset((page - 1) * per_page).limit(per_page).all()
        )
        return items, total

    def run_of(self, task: ScheduledTask, run_id: int) -> ScheduledTaskRun:
        run = self.db.query(ScheduledTaskRun).filter(
            ScheduledTaskRun.id == run_id, ScheduledTaskRun.scheduled_task_id == task.id
        ).one_or_none()
        if not run:
            raise ValueError("Scheduled task run not found")
        return run

    def run_now(self, task_id: int, app_id: int) -> str:
        task = self._task(task_id, app_id)
        if task.status != "active":
            raise ValueError("Only active scheduled tasks can be executed")
        if not self.orchestrator:
            raise ValueError("DBOS is not available")
        return self.orchestrator.run_task_now(task)

    # ------------------------------------------------------------------
    # Deletion and retention
    # ------------------------------------------------------------------

    async def delete(self, task_id: int, app_id: int) -> None:
        """Delete a task with its schedule, conversations, history, files and temp silos."""
        task = self._task(task_id, app_id)
        for agent_id, session_id in self._purge(task):
            await _delete_history(agent_id, session_id)

    def purge_for_agent(self, agent_id: int) -> None:
        """Delete every scheduled task of an agent (called from sync agent/app deletion)."""
        tasks = self.db.query(ScheduledTask).filter(ScheduledTask.agent_id == agent_id).all()
        threads: List[tuple] = []
        for task in tasks:
            threads.extend(self._purge(task))
        if threads:
            _run_in_background(_delete_histories(threads))

    def _purge(self, task: ScheduledTask) -> List[tuple]:
        """Remove the task and everything it owns. Returns the checkpointer threads to delete."""
        if self.orchestrator:
            try:
                self.orchestrator.delete_schedule(task.orchestrator_schedule_name)
            except Exception:
                logger.warning("Could not delete DBOS schedule %s", task.orchestrator_schedule_name, exc_info=True)
        task.persistent_conversation_id = None
        self.db.flush()
        conversations = self.db.query(Conversation).filter(Conversation.scheduled_task_id == task.id).all()
        threads = [self._release_conversation(task, conversation) for conversation in conversations]
        self.db.delete(task)
        self.db.commit()
        return threads

    def _release_conversation(self, task: ScheduledTask, conversation: Conversation) -> tuple:
        """Free a task conversation's files, temp silo and sandbox, then delete its row."""
        from services.conversation_service import ConversationService
        from services.file_management_service import FileManagementService

        ConversationService.release_conversation_resources(self.db, conversation)
        FileManagementService().delete_conversation_storage(
            conversation.agent_id, task_user_context(task), str(conversation.conversation_id)
        )
        thread = (conversation.agent_id, conversation.session_id)
        self.db.delete(conversation)
        return thread

    async def prune_runs(self, task: ScheduledTask) -> int:
        """Keep only the newest ``max_runs_retained`` finished runs; drop the older ones and their outputs."""
        from services.file_management_service import FileManagementService

        keep = max(1, task.max_runs_retained or 10)
        finished = (
            self.db.query(ScheduledTaskRun)
            .filter(ScheduledTaskRun.scheduled_task_id == task.id, ScheduledTaskRun.status.in_(_FINISHED_STATUSES))
            .order_by(ScheduledTaskRun.scheduled_time.desc(), ScheduledTaskRun.id.desc())
            .all()
        )
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        protected = {
            run.id for run in finished
            if any(
                delivery.status in {"pending", "sending", "retry_wait", "unknown"}
                and (not getattr(delivery, "expires_at", None) or delivery.expires_at.replace(tzinfo=None) > now)
                for delivery in getattr(run, "output_deliveries", [])
            )
        }
        stale = [run for run in finished[keep:] if run.id not in protected]
        if not stale:
            return 0
        kept_conversations = {run.conversation_id for run in finished[:keep]} | {task.persistent_conversation_id}
        threads = []
        files = FileManagementService()
        for run in stale:
            conversation = self.db.get(Conversation, run.conversation_id) if run.conversation_id else None
            if conversation is not None and conversation.conversation_id not in kept_conversations:
                threads.append(self._release_conversation(task, conversation))
            elif conversation is not None and run.output_files:
                # Continuous mode: the conversation lives on, only this run's files go.
                await files.remove_files(
                    [f["file_id"] for f in run.output_files if f.get("file_id")],
                    conversation.agent_id, task_user_context(task), str(conversation.conversation_id),
                )
            self.db.delete(run)
        self.db.commit()
        for agent_id, session_id in threads:
            await _delete_history(agent_id, session_id)
        return len(stale)

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------

    def _apply(self, task: ScheduledTask) -> None:
        if self.orchestrator:
            self.orchestrator.apply_task(task)

    def _pause(self, task: ScheduledTask) -> None:
        if self.orchestrator:
            self.orchestrator.pause_schedule(task.orchestrator_schedule_name)


def _visibility(value: Any) -> MarketplaceVisibility:
    if isinstance(value, MarketplaceVisibility):
        return value
    if not value:
        return MarketplaceVisibility.UNPUBLISHED
    return MarketplaceVisibility(str(value).lower())


async def _delete_history(agent_id: int, session_id: str) -> None:
    from services.conversation_service import ConversationService
    await ConversationService.delete_thread_history(agent_id, session_id)


async def _delete_histories(threads: List[tuple]) -> None:
    for agent_id, session_id in threads:
        await _delete_history(agent_id, session_id)


def _run_in_background(coro) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return
    task = loop.create_task(coro)
    _pending_cleanups.add(task)
    task.add_done_callback(_pending_cleanups.discard)
