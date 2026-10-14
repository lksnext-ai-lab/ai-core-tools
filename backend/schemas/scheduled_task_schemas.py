from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

VISIBILITY_PATTERN = "^(unpublished|private|public)$"


def _visibility_value(value: Any) -> Any:
    return getattr(value, "value", value)


class ScheduledTaskCreateSchema(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    agent_id: int
    input: Dict[str, Any] = Field(default_factory=dict)
    cron_expression: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="UTC", max_length=64)
    conversation_mode: str = Field(default="new_per_run", pattern="^(new_per_run|continuous)$")
    max_concurrent_runs: int = Field(default=1, ge=1, le=32)
    max_runs_retained: int = Field(default=10, ge=1, le=100)
    marketplace_visibility: str = Field(default="unpublished", pattern=VISIBILITY_PATTERN)
    output_bindings: list[Dict[str, Any]] = Field(default_factory=list, max_length=20)


class ScheduledTaskUpdateSchema(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    max_runs_retained: Optional[int] = Field(default=None, ge=1, le=100)
    marketplace_visibility: Optional[str] = Field(default=None, pattern=VISIBILITY_PATTERN)
    input: Optional[Dict[str, Any]] = None
    cron_expression: Optional[str] = Field(default=None, min_length=1, max_length=120)
    timezone: Optional[str] = Field(default=None, max_length=64)
    max_concurrent_runs: Optional[int] = Field(default=None, ge=1, le=32)
    status: Optional[str] = Field(default=None, pattern="^(active|paused)$")


class ScheduledTaskResponseSchema(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
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
    max_runs_retained: int
    marketplace_visibility: str
    created_at: datetime
    updated_at: datetime
    next_run_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

    _visibility = field_validator("marketplace_visibility", mode="before")(_visibility_value)


class ScheduledTaskRunFileSchema(BaseModel):
    file_id: str
    filename: str
    file_type: Optional[str] = None


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
    output_text: Optional[str] = None
    output_files: list[ScheduledTaskRunFileSchema] = Field(default_factory=list)
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


class ScheduledTaskFileDownloadSchema(BaseModel):
    download_url: str
    filename: str


class MarketplaceScheduledTaskCardSchema(BaseModel):
    """What the marketplace shows of a task: never its input or agent configuration."""
    id: int
    name: str
    description: Optional[str] = None
    app_id: int
    app_name: Optional[str] = None
    cron_expression: str
    timezone: str
    conversation_mode: str
    status: str
    marketplace_visibility: str
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    run_count: int = 0


class MarketplaceScheduledTaskCatalogSchema(BaseModel):
    tasks: list[MarketplaceScheduledTaskCardSchema]
    total: int
    page: int
    page_size: int
    total_pages: int
