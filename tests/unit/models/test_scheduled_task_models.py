from datetime import datetime, timezone

from models.agent_schedule import AgentSchedule
from models.scheduled_task import ScheduledTask


def test_scheduled_task_next_run_at_is_utc_for_active_valid_schedule():
    task = ScheduledTask(cron_expression="*/5 * * * *", timezone="Europe/Madrid", status="active")

    next_run = task.next_run_at

    assert next_run is not None
    assert next_run.utcoffset() == timezone.utc.utcoffset(next_run)
    assert isinstance(next_run, datetime)


def test_scheduled_task_next_run_at_is_none_when_paused_or_invalid():
    assert ScheduledTask(cron_expression="*/5 * * * *", timezone="UTC", status="paused").next_run_at is None
    assert ScheduledTask(cron_expression="invalid", timezone="UTC", status="active").next_run_at is None


def test_agent_schedule_next_run_at_handles_same_edge_cases():
    schedule = AgentSchedule(cron_expression="*/5 * * * *", timezone="UTC", status="active")
    assert schedule.next_run_at is not None
    schedule.status = "deleted"
    assert schedule.next_run_at is None
