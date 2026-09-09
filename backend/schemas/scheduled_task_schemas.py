from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ScheduledTaskCreateSchema(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    agent_id: int
    input: Dict[str, Any] = Field(default_factory=dict)
    cron_expression: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="UTC", max_length=64)
    conversation_mode: str = Field(default="new_per_run", pattern="^(new_per_run|continuous)$")
    max_concurrent_runs: int = Field(default=1, ge=1, le=32)


class ScheduledTaskUpdateSchema(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    input: Optional[Dict[str, Any]] = None
    cron_expression: Optional[str] = Field(default=None, min_length=1, max_length=120)
    timezone: Optional[str] = Field(default=None, max_length=64)
    max_concurrent_runs: Optional[int] = Field(default=None, ge=1, le=32)
    status: Optional[str] = Field(default=None, pattern="^(active|paused)$")


class ScheduledTaskResponseSchema(BaseModel):
    id: int
    name: str
    agent_id: int
    app_id: int
    created_by: int
    orchestrator_schedule_name: str
    input: Dict[str, Any]
    cron_expression: str
    timezone: str
    conversation_mode: str
    persistent_conversation_id: Optional[int]
    status: str
    max_concurrent_runs: int
    created_at: datetime
    updated_at: datetime
    next_run_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ScheduledTaskRunResponseSchema(BaseModel):
    id: int
    scheduled_task_id: int
    conversation_id: Optional[int]
    conversation_anchor_message_id: Optional[int]
    orchestrator_run_id: str
    scheduled_time: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    status: str
    attempt_count: int
    error_summary: Optional[str]
    model_config = ConfigDict(from_attributes=True)


class ScheduledTaskRunListSchema(BaseModel):
    items: list[ScheduledTaskRunResponseSchema]
    page: int
    per_page: int
    total: int


class ScheduledTaskTriggerResponseSchema(BaseModel):
    task_id: int
    workflow_id: str
    status: str = "queued"
