"""Domain adapter between agent scheduling and the DBOS runtime."""

from datetime import datetime, timezone
import os
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from sqlalchemy.orm import Session

from models.agent import Agent
from models.agent_schedule import AgentRunSummary, AgentSchedule


class AgentSchedulerService:
    MIN_INTERVAL_ENV = "AICT_MIN_SCHEDULE_INTERVAL_SECONDS"

    def __init__(self, db: Session, orchestrator=None):
        self.db = db
        self.orchestrator = orchestrator
        self.minimum_interval_seconds = int(os.getenv(self.MIN_INTERVAL_ENV, "60"))

    @staticmethod
    def schedule_name(schedule_id: int) -> str:
        return f"agent-schedule-{schedule_id}"

    @staticmethod
    def validate_cron(cron_expression: str, timezone_name: str, minimum_seconds: int = 60) -> None:
        try:
            tz = ZoneInfo(timezone_name)
            base = datetime.now(tz)
            iterator = croniter(cron_expression, base)
            first = iterator.get_next(datetime)
            second = iterator.get_next(datetime)
        except (ValueError, TypeError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Invalid cron expression or timezone") from exc
        if (second - first).total_seconds() < minimum_seconds:
            raise ValueError(f"Schedule interval must be at least {minimum_seconds} seconds")

    def _get_agent(self, agent_id: int, app_id: int) -> Agent:
        agent = self.db.query(Agent).filter(Agent.agent_id == agent_id, Agent.app_id == app_id).one_or_none()
        if not agent:
            raise ValueError("Agent not found")
        return agent

    def _get_schedule(self, schedule_id: int, agent_id: int, app_id: int) -> AgentSchedule:
        schedule = (
            self.db.query(AgentSchedule)
            .filter(AgentSchedule.id == schedule_id, AgentSchedule.agent_id == agent_id, AgentSchedule.app_id == app_id)
            .one_or_none()
        )
        if not schedule:
            raise ValueError("Schedule not found")
        return schedule

    def create_schedule(self, *, agent_id: int, app_id: int, created_by: int, cron_expression: str,
                        timezone_name: str = "UTC", input_context: Optional[Dict[str, Any]] = None,
                        max_concurrent_runs: int = 1) -> AgentSchedule:
        self._get_agent(agent_id, app_id)
        self.validate_cron(cron_expression, timezone_name, self.minimum_interval_seconds)
        schedule = AgentSchedule(
            agent_id=agent_id, app_id=app_id, created_by=created_by,
            orchestrator_schedule_name="pending", cron_expression=cron_expression,
            timezone=timezone_name, input_context=input_context,
            max_concurrent_runs=max_concurrent_runs,
        )
        self.db.add(schedule)
        self.db.flush()
        schedule.orchestrator_schedule_name = self.schedule_name(schedule.id)
        self._apply(schedule)
        self.db.commit()
        self.db.refresh(schedule)
        return schedule

    def list_schedules(self, agent_id: int, app_id: int):
        self._get_agent(agent_id, app_id)
        return self.db.query(AgentSchedule).filter(
            AgentSchedule.agent_id == agent_id, AgentSchedule.app_id == app_id,
            AgentSchedule.status != "deleted",
        ).order_by(AgentSchedule.created_at.desc()).all()

    def update_schedule(self, schedule_id: int, agent_id: int, app_id: int, changes: Dict[str, Any]) -> AgentSchedule:
        schedule = self._get_schedule(schedule_id, agent_id, app_id)
        cron_expression = changes.get("cron_expression", schedule.cron_expression)
        timezone_name = changes.get("timezone", schedule.timezone)
        self.validate_cron(cron_expression, timezone_name, self.minimum_interval_seconds)
        for key, value in changes.items():
            if value is not None and key in {"cron_expression", "timezone", "input_context", "max_concurrent_runs", "status"}:
                setattr(schedule, key, value)
        if schedule.status == "paused":
            self._pause(schedule)
        else:
            self._apply(schedule)
        self.db.commit()
        self.db.refresh(schedule)
        return schedule

    def delete_schedule(self, schedule_id: int, agent_id: int, app_id: int) -> None:
        schedule = self._get_schedule(schedule_id, agent_id, app_id)
        self._delete(schedule)
        schedule.status = "deleted"
        self.db.commit()

    def list_runs(self, schedule_id: int, agent_id: int, app_id: int, page: int = 1, per_page: int = 50):
        schedule = self._get_schedule(schedule_id, agent_id, app_id)
        query = self.db.query(AgentRunSummary).filter(AgentRunSummary.agent_schedule_id == schedule.id)
        total = query.count()
        items = query.order_by(AgentRunSummary.scheduled_time.desc()).offset((page - 1) * per_page).limit(per_page).all()
        return items, total

    def _apply(self, schedule: AgentSchedule) -> None:
        if self.orchestrator:
            self.orchestrator.apply_schedule(schedule)

    def _pause(self, schedule: AgentSchedule) -> None:
        if self.orchestrator:
            self.orchestrator.pause_schedule(schedule.orchestrator_schedule_name)

    def _delete(self, schedule: AgentSchedule) -> None:
        if self.orchestrator:
            self.orchestrator.delete_schedule(schedule.orchestrator_schedule_name)
