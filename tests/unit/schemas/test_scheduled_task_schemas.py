import pytest
from pydantic import ValidationError

from schemas.agent_schedule_schemas import AgentScheduleCreateSchema
from schemas.scheduled_task_schemas import ScheduledTaskCreateSchema, ScheduledTaskUpdateSchema


def test_scheduled_task_schema_defaults_and_conversation_mode_validation():
    schema = ScheduledTaskCreateSchema(name="Daily", agent_id=1, cron_expression="*/5 * * * *")
    assert schema.input == {}
    assert schema.timezone == "UTC"
    assert schema.conversation_mode == "new_per_run"
    with pytest.raises(ValidationError):
        ScheduledTaskCreateSchema(name="Daily", agent_id=1, cron_expression="x", conversation_mode="invalid")


def test_scheduled_task_schema_rejects_invalid_bounds_and_update_allows_unset_fields():
    with pytest.raises(ValidationError):
        ScheduledTaskCreateSchema(name="", agent_id=1, cron_expression="*/5 * * * *")
    with pytest.raises(ValidationError):
        ScheduledTaskCreateSchema(name="x", agent_id=1, cron_expression="x", max_concurrent_runs=33)
    assert ScheduledTaskUpdateSchema(status="paused").model_dump(exclude_unset=True) == {"status": "paused"}


def test_legacy_schedule_schema_has_optional_input_context_and_concurrency_bounds():
    schema = AgentScheduleCreateSchema(cron_expression="*/5 * * * *")
    assert schema.input_context is None
    with pytest.raises(ValidationError):
        AgentScheduleCreateSchema(cron_expression="x", max_concurrent_runs=0)
