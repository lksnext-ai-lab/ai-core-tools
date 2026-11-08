"""Adapters from scheduled-task ORM rows to provider-neutral connector messages."""

import os

from connectors.core.messages import RunMessage
from models.scheduled_task import ScheduledTask, ScheduledTaskRun


def base_url() -> str:
    """Public base URL used to build links back to Mattin AI."""
    return (os.getenv("FRONTEND_URL") or os.getenv("AICT_BASE_URL") or "http://localhost:5173").rstrip("/")


def run_message_from(task: ScheduledTask, run: ScheduledTaskRun) -> RunMessage:
    """Build the immutable ``RunMessage`` for one finished run."""
    return RunMessage(
        app_id=task.app_id,
        task_id=task.id,
        task_name=task.name,
        run_id=run.id,
        run_status=run.status,
        scheduled_time=run.scheduled_time,
        finished_at=run.finished_at,
        output_text=run.output_text or "",
        output_files=tuple(dict(item) for item in run.output_files or []),
        base_url=base_url(),
    )
