"""Application service for first-class scheduled tasks."""

import os
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from sqlalchemy.orm import Session

from models.agent import Agent
from models.scheduled_task import ScheduledTask, ScheduledTaskRun


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

    def create(self, *, app_id: int, created_by: int, data: Dict[str, Any]) -> ScheduledTask:
        self._agent(data["agent_id"], app_id)
        self.validate_cron(data["cron_expression"], data.get("timezone", "UTC"))
        task = ScheduledTask(
            app_id=app_id, created_by=created_by, name=data["name"], agent_id=data["agent_id"],
            input=data.get("input", {}), cron_expression=data["cron_expression"],
            timezone=data.get("timezone", "UTC"), conversation_mode=data.get("conversation_mode", "new_per_run"),
            max_concurrent_runs=data.get("max_concurrent_runs", 1),
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
        query = self.db.query(ScheduledTask).filter(ScheduledTask.app_id == app_id, ScheduledTask.status != "deleted")
        if agent_id is not None:
            query = query.filter(ScheduledTask.agent_id == agent_id)
        return query.order_by(ScheduledTask.created_at.desc()).all()

    def update(self, task_id: int, app_id: int, changes: Dict[str, Any]) -> ScheduledTask:
        task = self._task(task_id, app_id)
        cron = changes.get("cron_expression", task.cron_expression)
        timezone = changes.get("timezone", task.timezone)
        self.validate_cron(cron, timezone)
        for key, value in changes.items():
            if value is not None and key in {"name", "input", "cron_expression", "timezone", "max_concurrent_runs", "status"}:
                setattr(task, key, value)
        if task.status == "paused":
            self._pause(task)
        else:
            self._apply(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def delete(self, task_id: int, app_id: int) -> None:
        task = self._task(task_id, app_id)
        if self.orchestrator:
            self.orchestrator.delete_schedule(task.orchestrator_schedule_name)
        task.status = "deleted"
        self.db.commit()

    def runs(self, task_id: int, app_id: int, page: int, per_page: int):
        task = self._task(task_id, app_id)
        query = self.db.query(ScheduledTaskRun).filter(ScheduledTaskRun.scheduled_task_id == task.id)
        total = query.count()
        items = query.order_by(ScheduledTaskRun.scheduled_time.desc()).offset((page - 1) * per_page).limit(per_page).all()
        return items, total

    def run_now(self, task_id: int, app_id: int) -> str:
        task = self._task(task_id, app_id)
        if task.status != "active":
            raise ValueError("Only active scheduled tasks can be executed")
        if not self.orchestrator:
            raise ValueError("DBOS is not available")
        return self.orchestrator.run_task_now(task)

    def _apply(self, task: ScheduledTask) -> None:
        if self.orchestrator:
            self.orchestrator.apply_task(task)

    def _pause(self, task: ScheduledTask) -> None:
        if self.orchestrator:
            self.orchestrator.pause_schedule(task.orchestrator_schedule_name)
