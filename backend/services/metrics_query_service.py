"""Read path for the agent metrics dashboards (system, app and agent scopes).

Every query is scoped by a MetricsScope and a time window, and runs as one
aggregate statement (no per-row follow-up queries).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.agent import Agent
from models.agent_execution_event import AgentExecutionEvent as AEE
from models.agent_tool_call import AgentToolCall as ATC
from models.app import App
from models.enums.agent_execution_status import AgentExecutionStatus
from models.enums.agent_tool_call_status import AgentToolCallStatus
from models.user import User
from schemas.metrics_schemas import (
    BreakdownItem,
    BreakdownResponse,
    ErrorGroup,
    ErrorsResponse,
    RecentError,
    SummaryResponse,
    SummaryStats,
    TimeseriesPoint,
    TimeseriesResponse,
    ToolsResponse,
    ToolStats,
)

VALID_RANGES = ("24h", "7d", "30d", "90d")
BREAKDOWN_LIMIT = 50
TOOLS_LIMIT = 50
RECENT_ERRORS_LIMIT = 20

# range -> (window length, bucket label, bucket length)
_RANGES = {
    "24h": (timedelta(hours=24), "1h", timedelta(hours=1)),
    "7d": (timedelta(days=7), "6h", timedelta(hours=6)),
    "30d": (timedelta(days=30), "1d", timedelta(days=1)),
    "90d": (timedelta(days=90), "1d", timedelta(days=1)),
}


@dataclass(frozen=True)
class MetricsScope:
    """Which executions a query covers: all (system), one app, or one agent of an app."""
    app_id: Optional[int] = None
    agent_id: Optional[int] = None

    def filters(self) -> list:
        clauses = []
        if self.app_id is not None:
            clauses.append(AEE.app_id == self.app_id)
        if self.agent_id is not None:
            clauses.append(AEE.agent_id == self.agent_id)
        return clauses


def parse_range(range_str: str, now: Optional[datetime] = None) -> tuple[datetime, datetime, str, timedelta]:
    """Return (since, until, bucket_label, bucket_length) for a range key. Times are naive UTC."""
    if range_str not in _RANGES:
        raise ValueError(f"Invalid range: {range_str}")
    window, bucket_label, bucket_length = _RANGES[range_str]
    until = now or datetime.utcnow()
    return until - window, until, bucket_label, bucket_length


def _is_root():
    return AEE.parent_execution_id.is_(None)


def _is_error():
    return AEE.status == AgentExecutionStatus.ERROR


def _p(fraction: float, column):
    return func.percentile_cont(fraction).within_group(column.asc())


def _num(value) -> int:
    return int(value or 0)


def _opt_float(value) -> Optional[float]:
    return float(value) if value is not None else None


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _bucket_expression(bucket_label: str):
    if bucket_label == "1h":
        return func.date_trunc("hour", AEE.started_at)
    if bucket_label == "1d":
        return func.date_trunc("day", AEE.started_at)
    # 6-hour buckets aligned on UTC midnight; back to naive UTC like started_at.
    epoch = func.floor(func.extract("epoch", AEE.started_at) / 21600) * 21600
    return func.timezone("UTC", func.to_timestamp(epoch))


def _align(moment: datetime, bucket_length: timedelta) -> datetime:
    seconds = bucket_length.total_seconds()
    epoch = (moment - datetime(1970, 1, 1)).total_seconds()
    return datetime(1970, 1, 1) + timedelta(seconds=math.floor(epoch / seconds) * seconds)


class MetricsQueryService:

    @staticmethod
    def check_agent_in_app(db: Session, app_id: int, agent_id: int) -> None:
        exists = db.query(Agent.agent_id).filter(Agent.agent_id == agent_id, Agent.app_id == app_id).first()
        if not exists:
            raise HTTPException(status_code=404, detail="Agent not found in this app.")

    # ── summary ───────────────────────────────────────────────────────────

    @staticmethod
    def _summary_stats(db: Session, scope: MetricsScope, since: datetime, until: datetime) -> SummaryStats:
        window = [*scope.filters(), AEE.started_at >= since, AEE.started_at < until]
        root = _is_root()
        row = db.query(
            func.count().filter(root).label("executions"),
            func.count().filter(sa.not_(root)).label("subagent_calls"),
            func.count().filter(root, _is_error()).label("errors"),
            func.count().filter(root, AEE.status == AgentExecutionStatus.TIMEOUT).label("timeouts"),
            func.coalesce(func.sum(AEE.llm_calls), 0).label("llm_calls"),
            func.coalesce(func.sum(AEE.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AEE.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(AEE.total_tokens), 0).label("total_tokens"),
            _p(0.5, AEE.duration_ms).filter(root).label("p50"),
            _p(0.95, AEE.duration_ms).filter(root).label("p95"),
            _p(0.5, AEE.time_to_first_token_ms).filter(root).label("ttft_p50"),
            _p(0.95, AEE.time_to_first_token_ms).filter(root).label("ttft_p95"),
            func.count(func.distinct(AEE.app_id)).label("active_apps"),
            func.count(func.distinct(AEE.agent_id)).label("active_agents"),
            func.count(func.distinct(AEE.user_id)).label("active_users"),
        ).filter(*window).one()

        tools = db.query(
            func.count(ATC.tool_call_id).label("calls"),
            func.count(ATC.tool_call_id).filter(ATC.status == AgentToolCallStatus.ERROR).label("errors"),
        ).join(AEE, AEE.event_id == ATC.event_id).filter(*window).one()

        executions = _num(row.executions)
        errors = _num(row.errors)
        total_tokens = _num(row.total_tokens)
        return SummaryStats(
            executions=executions,
            subagent_calls=_num(row.subagent_calls),
            errors=errors,
            timeouts=_num(row.timeouts),
            error_rate=(errors / executions) if executions else 0.0,
            llm_calls=_num(row.llm_calls),
            input_tokens=_num(row.input_tokens),
            output_tokens=_num(row.output_tokens),
            total_tokens=total_tokens,
            avg_tokens_per_execution=(total_tokens / executions) if executions else None,
            latency_p50_ms=_opt_float(row.p50),
            latency_p95_ms=_opt_float(row.p95),
            ttft_p50_ms=_opt_float(row.ttft_p50),
            ttft_p95_ms=_opt_float(row.ttft_p95),
            tool_calls=_num(tools.calls),
            tool_errors=_num(tools.errors),
            active_apps=_num(row.active_apps),
            active_agents=_num(row.active_agents),
            active_users=_num(row.active_users),
        )

    @staticmethod
    def summary(db: Session, scope: MetricsScope, range_str: str) -> SummaryResponse:
        since, until, _, _ = parse_range(range_str)
        window = until - since
        return SummaryResponse(
            range=range_str,
            current=MetricsQueryService._summary_stats(db, scope, since, until),
            previous=MetricsQueryService._summary_stats(db, scope, since - window, since),
        )

    # ── time series ───────────────────────────────────────────────────────

    @staticmethod
    def timeseries(db: Session, scope: MetricsScope, range_str: str) -> TimeseriesResponse:
        since, until, bucket_label, bucket_length = parse_range(range_str)
        bucket = _bucket_expression(bucket_label).label("bucket")
        root = _is_root()
        rows = db.query(
            bucket,
            func.count().filter(root).label("executions"),
            func.count().filter(sa.not_(root)).label("subagent_calls"),
            func.count().filter(root, _is_error()).label("errors"),
            func.coalesce(func.sum(AEE.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AEE.output_tokens), 0).label("output_tokens"),
            _p(0.5, AEE.duration_ms).filter(root).label("p50"),
            _p(0.95, AEE.duration_ms).filter(root).label("p95"),
        ).filter(
            *scope.filters(), AEE.started_at >= since, AEE.started_at < until,
        ).group_by(bucket).all()
        by_bucket = {_align(r.bucket.replace(tzinfo=None), bucket_length): r for r in rows}

        # Gap-fill so charts show quiet periods as zero instead of skipping them.
        points = []
        cursor = _align(since, bucket_length)
        while cursor < until:
            r = by_bucket.get(cursor)
            points.append(TimeseriesPoint(
                ts=cursor.isoformat(),
                executions=_num(r.executions) if r else 0,
                subagent_calls=_num(r.subagent_calls) if r else 0,
                errors=_num(r.errors) if r else 0,
                input_tokens=_num(r.input_tokens) if r else 0,
                output_tokens=_num(r.output_tokens) if r else 0,
                latency_p50_ms=_opt_float(r.p50) if r else None,
                latency_p95_ms=_opt_float(r.p95) if r else None,
            ))
            cursor += bucket_length
        return TimeseriesResponse(range=range_str, bucket=bucket_label, points=points)

    # ── breakdowns ────────────────────────────────────────────────────────

    @staticmethod
    def breakdown(db: Session, scope: MetricsScope, range_str: str, dimension: str) -> BreakdownResponse:
        since, until, _, _ = parse_range(range_str)
        query_columns, joins, group_by, to_labels = _dimension(dimension)
        runs = func.count(AEE.event_id)
        query = db.query(
            *query_columns,
            runs.label("runs"),
            func.count().filter(_is_error()).label("errors"),
            func.coalesce(func.sum(AEE.llm_calls), 0).label("llm_calls"),
            func.coalesce(func.sum(AEE.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AEE.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(AEE.total_tokens), 0).label("total_tokens"),
            func.avg(AEE.duration_ms).label("avg_ms"),
            _p(0.95, AEE.duration_ms).label("p95_ms"),
            func.max(AEE.started_at).label("last_seen"),
        )
        for target, condition in joins:
            query = query.outerjoin(target, condition)
        rows = query.filter(
            *scope.filters(), AEE.started_at >= since, AEE.started_at < until,
        ).group_by(*group_by).order_by(runs.desc()).limit(BREAKDOWN_LIMIT).all()

        items = []
        for r in rows:
            key, label, secondary = to_labels(r)
            count = _num(r.runs)
            items.append(BreakdownItem(
                key=key,
                label=label,
                secondary_label=secondary,
                runs=count,
                errors=_num(r.errors),
                error_rate=(_num(r.errors) / count) if count else 0.0,
                llm_calls=_num(r.llm_calls),
                input_tokens=_num(r.input_tokens),
                output_tokens=_num(r.output_tokens),
                total_tokens=_num(r.total_tokens),
                avg_latency_ms=_opt_float(r.avg_ms),
                p95_latency_ms=_opt_float(r.p95_ms),
                last_seen=_iso(r.last_seen),
            ))
        return BreakdownResponse(range=range_str, dimension=dimension, items=items)

    # ── tools ─────────────────────────────────────────────────────────────

    @staticmethod
    def tools(db: Session, scope: MetricsScope, range_str: str) -> ToolsResponse:
        since, until, _, _ = parse_range(range_str)
        calls = func.count(ATC.tool_call_id)
        rows = db.query(
            ATC.tool_name,
            ATC.tool_type,
            calls.label("calls"),
            func.count(ATC.tool_call_id).filter(ATC.status == AgentToolCallStatus.ERROR).label("errors"),
            func.avg(ATC.duration_ms).label("avg_ms"),
            _p(0.95, ATC.duration_ms).label("p95_ms"),
        ).join(AEE, AEE.event_id == ATC.event_id).filter(
            *scope.filters(), AEE.started_at >= since, AEE.started_at < until,
        ).group_by(ATC.tool_name, ATC.tool_type).order_by(calls.desc()).limit(TOOLS_LIMIT).all()

        return ToolsResponse(range=range_str, tools=[
            ToolStats(
                tool_name=r.tool_name,
                tool_type=_enum_value(r.tool_type),
                calls=_num(r.calls),
                errors=_num(r.errors),
                error_rate=(_num(r.errors) / _num(r.calls)) if r.calls else 0.0,
                avg_duration_ms=_opt_float(r.avg_ms),
                p95_duration_ms=_opt_float(r.p95_ms),
            )
            for r in rows
        ])

    # ── errors ────────────────────────────────────────────────────────────

    @staticmethod
    def errors(db: Session, scope: MetricsScope, range_str: str) -> ErrorsResponse:
        since, until, _, _ = parse_range(range_str)
        window = [*scope.filters(), AEE.started_at >= since, AEE.started_at < until, _is_error()]
        code = func.coalesce(AEE.error_code, "UNKNOWN").label("code")
        count = func.count(AEE.event_id)
        groups = db.query(
            code,
            count.label("count"),
            func.max(AEE.started_at).label("last_seen"),
            func.max(AEE.error_message).label("sample"),
        ).filter(*window).group_by(code).order_by(count.desc()).limit(BREAKDOWN_LIMIT).all()

        recent = db.query(
            AEE.started_at, AEE.app_id, App.name.label("app_name"), AEE.agent_id,
            Agent.name.label("agent_name"), AEE.caller_type, AEE.error_code, AEE.error_message,
        ).outerjoin(App, App.app_id == AEE.app_id).outerjoin(Agent, Agent.agent_id == AEE.agent_id).filter(
            *window
        ).order_by(AEE.started_at.desc()).limit(RECENT_ERRORS_LIMIT).all()

        return ErrorsResponse(
            range=range_str,
            groups=[
                ErrorGroup(
                    error_code=g.code,
                    count=_num(g.count),
                    last_seen=_iso(g.last_seen),
                    sample_message=(g.sample or None) and g.sample[:500],
                )
                for g in groups
            ],
            recent=[
                RecentError(
                    started_at=_iso(r.started_at),
                    app_id=r.app_id,
                    app_name=r.app_name,
                    agent_id=r.agent_id,
                    agent_name=r.agent_name,
                    caller_type=_enum_value(r.caller_type),
                    error_code=r.error_code,
                    error_message=(r.error_message or None) and r.error_message[:500],
                )
                for r in recent
            ],
        )


def _enum_value(value) -> str:
    return getattr(value, "value", value)


def _dimension(dimension: str):
    """Columns, outer joins, GROUP BY and a row -> (key, label, secondary) mapper for a breakdown."""
    if dimension == "app":
        return (
            [AEE.app_id, App.name.label("name")],
            [(App, App.app_id == AEE.app_id)],
            [AEE.app_id, App.name],
            lambda r: (str(r.app_id), r.name or f"App #{r.app_id}", None),
        )
    if dimension == "agent":
        return (
            [AEE.agent_id, Agent.name.label("name"), App.name.label("app_name")],
            [(Agent, Agent.agent_id == AEE.agent_id), (App, App.app_id == AEE.app_id)],
            [AEE.agent_id, Agent.name, App.name],
            lambda r: (str(r.agent_id), r.name or f"Agent #{r.agent_id}", r.app_name),
        )
    if dimension == "user":
        return (
            [AEE.user_id, User.email.label("email")],
            [(User, User.user_id == AEE.user_id)],
            [AEE.user_id, User.email],
            lambda r: (
                str(r.user_id) if r.user_id is not None else "none",
                r.email or ("API key / MCP" if r.user_id is None else f"User #{r.user_id}"),
                None,
            ),
        )
    if dimension == "channel":
        return (
            [AEE.caller_type],
            [],
            [AEE.caller_type],
            lambda r: (_enum_value(r.caller_type), _enum_value(r.caller_type), None),
        )
    if dimension in ("model", "provider"):
        column = func.coalesce(AEE.model_name if dimension == "model" else AEE.provider, "unknown").label("value")
        return ([column], [], [column], lambda r: (r.value, r.value, None))
    raise ValueError(f"Invalid dimension: {dimension}")
