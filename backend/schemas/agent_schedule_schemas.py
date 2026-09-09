from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentScheduleCreateSchema(BaseModel):
    cron_expression: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="UTC", max_length=64)
    input_context: Optional[Dict[str, Any]] = None
    max_concurrent_runs: int = Field(default=1, ge=1, le=32)


class AgentScheduleUpdateSchema(BaseModel):
    cron_expression: Optional[str] = Field(default=None, min_length=1, max_length=120)
    timezone: Optional[str] = Field(default=None, max_length=64)
    input_context: Optional[Dict[str, Any]] = None
    max_concurrent_runs: Optional[int] = Field(default=None, ge=1, le=32)
    status: Optional[str] = Field(default=None, pattern="^(active|paused)$")


class AgentScheduleResponseSchema(BaseModel):
    id: int
    agent_id: int
    app_id: int
    created_by: int
    orchestrator_schedule_name: str
    cron_expression: str
    timezone: str
    input_context: Optional[Dict[str, Any]]
    status: str
    max_concurrent_runs: int
    created_at: datetime
    updated_at: datetime
    next_run_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AgentRunSummaryResponseSchema(BaseModel):
    id: int
    agent_schedule_id: int
    orchestrator_run_id: str
    scheduled_time: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    status: str
    attempt_count: int
    error_summary: Optional[str]
    output_summary: Optional[Dict[str, Any]]

    model_config = ConfigDict(from_attributes=True)


class AgentRunSummaryListSchema(BaseModel):
    items: List[AgentRunSummaryResponseSchema]
    page: int
    per_page: int
    total: int
