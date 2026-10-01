"""Pydantic response schemas for the agent metrics dashboards.

The same shapes serve the three scopes (system, app, agent). "runs" count every
recorded agent execution; "executions" count only top-level ones (sub-agent
calls excluded). Token and LLM-call totals sum all runs: each run records only
its own direct LLM calls, so nothing is counted twice.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

MetricsRange = Literal["24h", "7d", "30d", "90d"]
BreakdownDimension = Literal["app", "agent", "model", "provider", "channel", "user"]


class SummaryStats(BaseModel):
    executions: int
    subagent_calls: int
    errors: int
    timeouts: int
    error_rate: float
    llm_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    avg_tokens_per_execution: Optional[float] = None
    latency_p50_ms: Optional[float] = None
    latency_p95_ms: Optional[float] = None
    ttft_p50_ms: Optional[float] = None
    ttft_p95_ms: Optional[float] = None
    tool_calls: int
    tool_errors: int
    active_apps: int
    active_agents: int
    active_users: int


class SummaryResponse(BaseModel):
    range: MetricsRange
    current: SummaryStats
    previous: SummaryStats  # same-length window right before the current one


class TimeseriesPoint(BaseModel):
    ts: str  # bucket start, ISO-8601 UTC
    executions: int
    subagent_calls: int
    errors: int
    input_tokens: int
    output_tokens: int
    latency_p50_ms: Optional[float] = None
    latency_p95_ms: Optional[float] = None


class TimeseriesResponse(BaseModel):
    range: MetricsRange
    bucket: Literal["1h", "6h", "1d"]
    points: list[TimeseriesPoint]


class BreakdownItem(BaseModel):
    key: str
    label: str
    secondary_label: Optional[str] = None  # e.g. the app of an agent in the system view
    runs: int
    errors: int
    error_rate: float
    llm_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    avg_latency_ms: Optional[float] = None
    p95_latency_ms: Optional[float] = None
    last_seen: Optional[str] = None


class BreakdownResponse(BaseModel):
    range: MetricsRange
    dimension: BreakdownDimension
    items: list[BreakdownItem]


class ToolStats(BaseModel):
    tool_name: str
    tool_type: str
    calls: int
    errors: int
    error_rate: float
    avg_duration_ms: Optional[float] = None
    p95_duration_ms: Optional[float] = None


class ToolsResponse(BaseModel):
    range: MetricsRange
    tools: list[ToolStats]


class ErrorGroup(BaseModel):
    error_code: str
    count: int
    last_seen: str
    sample_message: Optional[str] = None


class RecentError(BaseModel):
    started_at: str
    app_id: int
    app_name: Optional[str] = None
    agent_id: int
    agent_name: Optional[str] = None
    caller_type: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class ErrorsResponse(BaseModel):
    range: MetricsRange
    groups: list[ErrorGroup]
    recent: list[RecentError]
