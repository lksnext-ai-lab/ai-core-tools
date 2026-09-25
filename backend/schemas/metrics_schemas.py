"""Pydantic response schemas for the agent metrics dashboard."""
from __future__ import annotations
from typing import Optional, Literal
from pydantic import BaseModel

TimeRange = Literal["24h", "7d", "30d"]

# ── App-level schemas ──────────────────────────────────────────────────────

class AppSummaryResponse(BaseModel):
    range: str
    total_executions: int
    total_executions_incl_subcalls: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    error_rate: float
    avg_latency_ms_p50: Optional[float]
    avg_latency_ms_p95: Optional[float]
    active_agents: int
    active_users: int


class ExecutionBucket(BaseModel):
    ts: str
    root: int
    sub: int
    errors: int


class AppExecutionsResponse(BaseModel):
    range: str
    bucket_size: str
    series: list[ExecutionBucket]


class AgentBreakdown(BaseModel):
    agent_id: int
    agent_name: str
    executions: int
    total_tokens: int
    error_rate: float
    avg_latency_ms: Optional[float]
    last_execution_at: Optional[str]


class AppAgentsResponse(BaseModel):
    range: str
    agents: list[AgentBreakdown]


class ModelBreakdown(BaseModel):
    model_name: str
    executions: int
    total_tokens: int
    input_tokens: int
    output_tokens: int
    error_rate: float
    avg_latency_ms: Optional[float]
    last_execution_at: Optional[str]


class AppModelsResponse(BaseModel):
    range: str
    models: list[ModelBreakdown]


class UserBreakdown(BaseModel):
    user_id: Optional[int]
    user_name: Optional[str]
    executions: int
    total_tokens: int


class AppUsersResponse(BaseModel):
    range: str
    users: list[UserBreakdown]
    limit: int


# ── Per-agent schemas ──────────────────────────────────────────────────────

class AgentSummaryResponse(BaseModel):
    range: str
    executions: int
    executions_incl_subcalls: int
    total_tokens: int
    input_tokens: int
    output_tokens: int
    error_rate: float
    latency_p50_ms: Optional[float]
    latency_p95_ms: Optional[float]
    latency_p99_ms: Optional[float]
    active_users: int


class AgentExecutionBucket(BaseModel):
    ts: str
    root: int
    as_tool: int


class AgentExecutionsResponse(BaseModel):
    range: str
    bucket_size: str
    series: list[AgentExecutionBucket]


class TokenBucket(BaseModel):
    ts: str
    input: int
    output: int


class AgentTokensResponse(BaseModel):
    range: str
    bucket_size: str
    series: list[TokenBucket]


class ErrorBucket(BaseModel):
    ts: str
    errors: int
    total: int
    rate: float


class ErrorByCode(BaseModel):
    error_code: str
    count: int


class AgentErrorsResponse(BaseModel):
    range: str
    bucket_size: str
    series: list[ErrorBucket]
    by_code: list[ErrorByCode]


class LatencyBucket(BaseModel):
    ts: str
    p50: Optional[float]
    p95: Optional[float]
    p99: Optional[float]


class AgentLatencyResponse(BaseModel):
    range: str
    bucket_size: str
    series: list[LatencyBucket]


class ToolBreakdown(BaseModel):
    tool_name: str
    tool_type: str
    sub_agent_id: Optional[int] = None
    calls: int
    error_rate: float
    avg_duration_ms: Optional[float]


class AgentToolsResponse(BaseModel):
    range: str
    tools: list[ToolBreakdown]


class AgentUsersResponse(BaseModel):
    range: str
    users: list[UserBreakdown]
    limit: int
