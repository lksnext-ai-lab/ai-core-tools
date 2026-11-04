"""Row factories for the scheduled-task output outbox tests."""

import base64
from datetime import datetime

from models.output_delivery import OutputDestination
from models.scheduled_task import ScheduledTask, ScheduledTaskRun

TEAMS_URL = "https://prod.logic.azure.com/workflows/abc/triggers/manual?sig=secret"
WEBHOOK_URL = "https://hooks.example.com/mattin"
HMAC_SECRET = base64.b64encode(b"k" * 32).decode("ascii")


def make_task(task_id=1, *, app_id=1, name="Daily"):
    return ScheduledTask(id=task_id, app_id=app_id, agent_id=1, created_by=1, name=name,
                         cron_expression="0 8 * * *", orchestrator_schedule_name=f"task-{task_id}")


def make_run(run_id=1, *, task_id=1, text="Result", files=None, reconciled=True):
    return ScheduledTaskRun(id=run_id, scheduled_task_id=task_id, status="succeeded",
                            scheduled_time=datetime(2026, 10, 1, 8, 0), orchestrator_run_id=f"run-{run_id}",
                            output_text=text, output_files=files or [], outputs_reconciled=reconciled)


def make_destination(destination_id=1, *, provider_key="teams_workflow", name=None, config=None,
                     credentials=None, content_mode="result", enabled=True, url=None):
    return OutputDestination(
        id=destination_id, app_id=1, created_by=1, name=name or f"Channel {destination_id}",
        provider_key=provider_key, content_mode=content_mode, enabled=enabled,
        public_config=config or {}, credentials=credentials,
        webhook_url=url or (WEBHOOK_URL if provider_key == "webhook" else TEAMS_URL),
    )
