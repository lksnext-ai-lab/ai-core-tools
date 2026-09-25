"""MetricsQueryService — read path for the agent metrics dashboard."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from schemas.metrics_schemas import (
    AppSummaryResponse, AppExecutionsResponse, AppAgentsResponse, AppUsersResponse,
    AppModelsResponse, ModelBreakdown,
    AgentSummaryResponse, AgentExecutionsResponse, AgentTokensResponse,
    AgentErrorsResponse, AgentLatencyResponse, AgentToolsResponse, AgentUsersResponse,
    ExecutionBucket, AgentBreakdown, UserBreakdown,
    AgentExecutionBucket, TokenBucket, ErrorBucket, ErrorByCode,
    LatencyBucket, ToolBreakdown,
)


def _parse_range(range_str: str) -> tuple:
    """Returns (since_utc, bucket_label, bucket_sql_expr)."""
    now = datetime.utcnow()
    if range_str == "24h":
        return now - timedelta(hours=24), "1h", "date_trunc('hour', started_at)"
    if range_str == "7d":
        return now - timedelta(days=7), "6h", (
            "to_timestamp(floor(extract(epoch from started_at)/21600)*21600)"
        )
    if range_str == "30d":
        return now - timedelta(days=30), "1d", "date_trunc('day', started_at)"
    raise ValueError(f"Invalid range: {range_str}")


class MetricsQueryService:

    @staticmethod
    def app_summary(db: Session, app_id: int, range_str: str) -> AppSummaryResponse:
        from models.agent_execution_event import AgentExecutionEvent as AEE

        since, bucket_label, _ = _parse_range(range_str)

        q = db.query(
            func.count(AEE.event_id).label('total'),
            func.coalesce(func.sum(AEE.input_tokens), 0).label('input_tokens'),
            func.coalesce(func.sum(AEE.output_tokens), 0).label('output_tokens'),
            func.coalesce(func.sum(AEE.total_tokens), 0).label('total_tokens'),
            func.count(func.distinct(AEE.agent_id)).label('active_agents'),
            func.count(func.distinct(AEE.user_id)).label('active_users'),
            func.percentile_cont(0.5).within_group(AEE.duration_ms.asc()).label('p50'),
            func.percentile_cont(0.95).within_group(AEE.duration_ms.asc()).label('p95'),
        ).filter(
            AEE.app_id == app_id,
            AEE.started_at >= since,
        ).one()

        error_count = db.query(func.count(AEE.event_id)).filter(
            AEE.app_id == app_id,
            AEE.started_at >= since,
            AEE.status == 'ERROR',
        ).scalar() or 0

        total = q.total or 0
        error_rate = (error_count / total) if total > 0 else 0.0

        return AppSummaryResponse(
            range=range_str,
            total_executions=total,
            total_executions_incl_subcalls=total,
            total_input_tokens=q.input_tokens or 0,
            total_output_tokens=q.output_tokens or 0,
            total_tokens=q.total_tokens or 0,
            error_rate=error_rate,
            avg_latency_ms_p50=q.p50,
            avg_latency_ms_p95=q.p95,
            active_agents=q.active_agents or 0,
            active_users=q.active_users or 0,
        )

    @staticmethod
    def app_executions(db: Session, app_id: int, range_str: str,
                       caller_type: Optional[str] = None) -> AppExecutionsResponse:
        from models.agent_execution_event import AgentExecutionEvent as AEE

        since, bucket_label, bucket_expr = _parse_range(range_str)

        bucket_col = sa.literal_column(bucket_expr).label('ts')
        filters = [AEE.app_id == app_id, AEE.started_at >= since]
        if caller_type:
            filters.append(AEE.caller_type == caller_type)

        rows = db.query(
            bucket_col,
            func.count(sa.case((AEE.parent_execution_id == None, 1))).label('root'),
            func.count(sa.case((AEE.parent_execution_id != None, 1))).label('sub'),
            func.count(sa.case((AEE.status == 'ERROR', 1))).label('errors'),
        ).filter(*filters).group_by(bucket_col).order_by(bucket_col).all()

        series = [
            ExecutionBucket(
                ts=str(r.ts),
                root=r.root or 0,
                sub=r.sub or 0,
                errors=r.errors or 0,
            )
            for r in rows
        ]
        return AppExecutionsResponse(range=range_str, bucket_size=bucket_label, series=series)

    @staticmethod
    def app_agents(db: Session, app_id: int, range_str: str) -> AppAgentsResponse:
        from models.agent_execution_event import AgentExecutionEvent as AEE
        from models.agent import Agent as AgentModel

        since, _, _ = _parse_range(range_str)

        rows = db.query(
            AEE.agent_id,
            AgentModel.name.label('agent_name'),
            func.count(AEE.event_id).label('executions'),
            func.coalesce(func.sum(AEE.total_tokens), 0).label('total_tokens'),
            func.avg(AEE.duration_ms).label('avg_latency_ms'),
            func.max(AEE.started_at).label('last_execution_at'),
        ).join(AgentModel, AgentModel.agent_id == AEE.agent_id).filter(
            AEE.app_id == app_id,
            AEE.started_at >= since,
        ).group_by(AEE.agent_id, AgentModel.name).order_by(
            func.count(AEE.event_id).desc()
        ).all()

        agents = []
        for r in rows:
            total = r.executions or 0
            error_count = db.query(func.count(AEE.event_id)).filter(
                AEE.app_id == app_id,
                AEE.agent_id == r.agent_id,
                AEE.started_at >= since,
                AEE.status == 'ERROR',
            ).scalar() or 0
            error_rate = (error_count / total) if total > 0 else 0.0
            agents.append(AgentBreakdown(
                agent_id=r.agent_id,
                agent_name=r.agent_name or '',
                executions=total,
                total_tokens=r.total_tokens or 0,
                error_rate=error_rate,
                avg_latency_ms=r.avg_latency_ms,
                last_execution_at=str(r.last_execution_at) if r.last_execution_at else None,
            ))

        return AppAgentsResponse(range=range_str, agents=agents)

    @staticmethod
    def app_models(db: Session, app_id: int, range_str: str) -> AppModelsResponse:
        from models.agent_execution_event import AgentExecutionEvent as AEE

        since, _, _ = _parse_range(range_str)

        rows = db.query(
            func.coalesce(AEE.model_name, 'unknown').label('model_name'),
            func.count(AEE.event_id).label('executions'),
            func.coalesce(func.sum(AEE.total_tokens), 0).label('total_tokens'),
            func.coalesce(func.sum(AEE.input_tokens), 0).label('input_tokens'),
            func.coalesce(func.sum(AEE.output_tokens), 0).label('output_tokens'),
            func.avg(AEE.duration_ms).label('avg_latency_ms'),
            func.max(AEE.started_at).label('last_execution_at'),
            func.count(
                AEE.event_id
            ).filter(AEE.status == 'ERROR').label('error_count'),
        ).filter(
            AEE.app_id == app_id,
            AEE.started_at >= since,
            AEE.parent_execution_id.is_(None),  # root executions only
        ).group_by(
            func.coalesce(AEE.model_name, 'unknown')
        ).order_by(
            func.count(AEE.event_id).desc()
        ).all()

        models = []
        for r in rows:
            total = r.executions or 0
            error_rate = (r.error_count / total) if total > 0 else 0.0
            models.append(ModelBreakdown(
                model_name=r.model_name,
                executions=total,
                total_tokens=r.total_tokens or 0,
                input_tokens=r.input_tokens or 0,
                output_tokens=r.output_tokens or 0,
                error_rate=error_rate,
                avg_latency_ms=r.avg_latency_ms,
                last_execution_at=str(r.last_execution_at) if r.last_execution_at else None,
            ))

        return AppModelsResponse(range=range_str, models=models)

    @staticmethod
    def app_users(db: Session, app_id: int, range_str: str, limit: int = 20) -> AppUsersResponse:
        from models.agent_execution_event import AgentExecutionEvent as AEE
        from models.user import User as UserModel

        since, _, _ = _parse_range(range_str)

        rows = db.query(
            AEE.user_id,
            UserModel.email.label('user_name'),
            func.count(AEE.event_id).label('executions'),
            func.coalesce(func.sum(AEE.total_tokens), 0).label('total_tokens'),
        ).outerjoin(UserModel, UserModel.user_id == AEE.user_id).filter(
            AEE.app_id == app_id,
            AEE.started_at >= since,
        ).group_by(AEE.user_id, UserModel.email).order_by(
            func.count(AEE.event_id).desc()
        ).limit(limit).all()

        users = [
            UserBreakdown(
                user_id=r.user_id,
                user_name=r.user_name,
                executions=r.executions or 0,
                total_tokens=r.total_tokens or 0,
            )
            for r in rows
        ]
        return AppUsersResponse(range=range_str, users=users, limit=limit)

    @staticmethod
    def _check_agent_in_app(db: Session, app_id: int, agent_id: int):
        from models.agent import Agent as AgentModel
        from fastapi import HTTPException
        agent = db.query(AgentModel).filter(
            AgentModel.agent_id == agent_id,
            AgentModel.app_id == app_id,
        ).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found in this app.")
        return agent

    @staticmethod
    def agent_summary(db: Session, app_id: int, agent_id: int,
                      range_str: str) -> AgentSummaryResponse:
        from models.agent_execution_event import AgentExecutionEvent as AEE

        MetricsQueryService._check_agent_in_app(db, app_id, agent_id)
        since, _, _ = _parse_range(range_str)

        q = db.query(
            func.count(AEE.event_id).label('total'),
            func.coalesce(func.sum(AEE.input_tokens), 0).label('input_tokens'),
            func.coalesce(func.sum(AEE.output_tokens), 0).label('output_tokens'),
            func.coalesce(func.sum(AEE.total_tokens), 0).label('total_tokens'),
            func.count(func.distinct(AEE.user_id)).label('active_users'),
            func.percentile_cont(0.5).within_group(AEE.duration_ms.asc()).label('p50'),
            func.percentile_cont(0.95).within_group(AEE.duration_ms.asc()).label('p95'),
            func.percentile_cont(0.99).within_group(AEE.duration_ms.asc()).label('p99'),
        ).filter(
            AEE.agent_id == agent_id,
            AEE.app_id == app_id,
            AEE.started_at >= since,
        ).one()

        error_count = db.query(func.count(AEE.event_id)).filter(
            AEE.agent_id == agent_id,
            AEE.app_id == app_id,
            AEE.started_at >= since,
            AEE.status == 'ERROR',
        ).scalar() or 0

        total = q.total or 0
        error_rate = (error_count / total) if total > 0 else 0.0

        return AgentSummaryResponse(
            range=range_str,
            executions=total,
            executions_incl_subcalls=total,
            total_tokens=q.total_tokens or 0,
            input_tokens=q.input_tokens or 0,
            output_tokens=q.output_tokens or 0,
            error_rate=error_rate,
            latency_p50_ms=q.p50,
            latency_p95_ms=q.p95,
            latency_p99_ms=q.p99,
            active_users=q.active_users or 0,
        )

    @staticmethod
    def agent_executions(db: Session, app_id: int, agent_id: int,
                         range_str: str) -> AgentExecutionsResponse:
        from models.agent_execution_event import AgentExecutionEvent as AEE

        MetricsQueryService._check_agent_in_app(db, app_id, agent_id)
        since, bucket_label, bucket_expr = _parse_range(range_str)

        bucket_col = sa.literal_column(bucket_expr).label('ts')
        rows = db.query(
            bucket_col,
            func.count(sa.case((AEE.parent_execution_id == None, 1))).label('root'),
            func.count(sa.case((AEE.parent_execution_id != None, 1))).label('as_tool'),
        ).filter(
            AEE.agent_id == agent_id,
            AEE.app_id == app_id,
            AEE.started_at >= since,
        ).group_by(bucket_col).order_by(bucket_col).all()

        series = [
            AgentExecutionBucket(ts=str(r.ts), root=r.root or 0, as_tool=r.as_tool or 0)
            for r in rows
        ]
        return AgentExecutionsResponse(range=range_str, bucket_size=bucket_label, series=series)

    @staticmethod
    def agent_tokens(db: Session, app_id: int, agent_id: int,
                     range_str: str) -> AgentTokensResponse:
        from models.agent_execution_event import AgentExecutionEvent as AEE

        MetricsQueryService._check_agent_in_app(db, app_id, agent_id)
        since, bucket_label, bucket_expr = _parse_range(range_str)

        bucket_col = sa.literal_column(bucket_expr).label('ts')
        rows = db.query(
            bucket_col,
            func.coalesce(func.sum(AEE.input_tokens), 0).label('input'),
            func.coalesce(func.sum(AEE.output_tokens), 0).label('output'),
        ).filter(
            AEE.agent_id == agent_id,
            AEE.app_id == app_id,
            AEE.started_at >= since,
        ).group_by(bucket_col).order_by(bucket_col).all()

        series = [
            TokenBucket(ts=str(r.ts), input=r.input or 0, output=r.output or 0)
            for r in rows
        ]
        return AgentTokensResponse(range=range_str, bucket_size=bucket_label, series=series)

    @staticmethod
    def agent_errors(db: Session, app_id: int, agent_id: int,
                     range_str: str) -> AgentErrorsResponse:
        from models.agent_execution_event import AgentExecutionEvent as AEE

        MetricsQueryService._check_agent_in_app(db, app_id, agent_id)
        since, bucket_label, bucket_expr = _parse_range(range_str)

        bucket_col = sa.literal_column(bucket_expr).label('ts')
        rows = db.query(
            bucket_col,
            func.count(sa.case((AEE.status == 'ERROR', 1))).label('errors'),
            func.count(AEE.event_id).label('total'),
        ).filter(
            AEE.agent_id == agent_id,
            AEE.app_id == app_id,
            AEE.started_at >= since,
        ).group_by(bucket_col).order_by(bucket_col).all()

        series = [
            ErrorBucket(
                ts=str(r.ts),
                errors=r.errors or 0,
                total=r.total or 0,
                rate=(r.errors / r.total) if r.total else 0.0,
            )
            for r in rows
        ]

        by_code_rows = db.query(
            AEE.error_code,
            func.count(AEE.event_id).label('count'),
        ).filter(
            AEE.agent_id == agent_id,
            AEE.app_id == app_id,
            AEE.started_at >= since,
            AEE.error_code != None,
        ).group_by(AEE.error_code).order_by(func.count(AEE.event_id).desc()).all()

        by_code = [ErrorByCode(error_code=r.error_code, count=r.count) for r in by_code_rows]

        return AgentErrorsResponse(range=range_str, bucket_size=bucket_label, series=series, by_code=by_code)

    @staticmethod
    def agent_latency(db: Session, app_id: int, agent_id: int,
                      range_str: str) -> AgentLatencyResponse:
        from models.agent_execution_event import AgentExecutionEvent as AEE

        MetricsQueryService._check_agent_in_app(db, app_id, agent_id)
        since, bucket_label, bucket_expr = _parse_range(range_str)

        bucket_col = sa.literal_column(bucket_expr).label('ts')
        rows = db.query(
            bucket_col,
            func.percentile_cont(0.5).within_group(AEE.duration_ms.asc()).label('p50'),
            func.percentile_cont(0.95).within_group(AEE.duration_ms.asc()).label('p95'),
            func.percentile_cont(0.99).within_group(AEE.duration_ms.asc()).label('p99'),
        ).filter(
            AEE.agent_id == agent_id,
            AEE.app_id == app_id,
            AEE.started_at >= since,
        ).group_by(bucket_col).order_by(bucket_col).all()

        series = [
            LatencyBucket(ts=str(r.ts), p50=r.p50, p95=r.p95, p99=r.p99)
            for r in rows
        ]
        return AgentLatencyResponse(range=range_str, bucket_size=bucket_label, series=series)

    @staticmethod
    def agent_tools(db: Session, app_id: int, agent_id: int,
                    range_str: str, limit: int = 20) -> AgentToolsResponse:
        from models.agent_execution_event import AgentExecutionEvent as AEE
        from models.agent_tool_call import AgentToolCall as ATC

        MetricsQueryService._check_agent_in_app(db, app_id, agent_id)
        since, _, _ = _parse_range(range_str)

        rows = db.query(
            ATC.tool_name,
            ATC.tool_type,
            ATC.sub_agent_id,
            func.count(ATC.tool_call_id).label('calls'),
            func.count(sa.case((ATC.status == 'ERROR', 1))).label('errors'),
            func.avg(ATC.duration_ms).label('avg_duration_ms'),
        ).join(AEE, AEE.event_id == ATC.event_id).filter(
            AEE.agent_id == agent_id,
            AEE.app_id == app_id,
            AEE.started_at >= since,
        ).group_by(ATC.tool_name, ATC.tool_type, ATC.sub_agent_id).order_by(
            func.count(ATC.tool_call_id).desc()
        ).limit(limit).all()

        tools = [
            ToolBreakdown(
                tool_name=r.tool_name,
                tool_type=str(r.tool_type) if r.tool_type else '',
                sub_agent_id=r.sub_agent_id,
                calls=r.calls or 0,
                error_rate=(r.errors / r.calls) if r.calls else 0.0,
                avg_duration_ms=r.avg_duration_ms,
            )
            for r in rows
        ]
        return AgentToolsResponse(range=range_str, tools=tools)

    @staticmethod
    def agent_users(db: Session, app_id: int, agent_id: int,
                    range_str: str, limit: int = 20) -> AgentUsersResponse:
        from models.agent_execution_event import AgentExecutionEvent as AEE
        from models.user import User as UserModel

        MetricsQueryService._check_agent_in_app(db, app_id, agent_id)
        since, _, _ = _parse_range(range_str)

        rows = db.query(
            AEE.user_id,
            UserModel.email.label('user_name'),
            func.count(AEE.event_id).label('executions'),
            func.coalesce(func.sum(AEE.total_tokens), 0).label('total_tokens'),
        ).outerjoin(UserModel, UserModel.user_id == AEE.user_id).filter(
            AEE.agent_id == agent_id,
            AEE.app_id == app_id,
            AEE.started_at >= since,
        ).group_by(AEE.user_id, UserModel.email).order_by(
            func.count(AEE.event_id).desc()
        ).limit(limit).all()

        users = [
            UserBreakdown(
                user_id=r.user_id,
                user_name=r.user_name,
                executions=r.executions or 0,
                total_tokens=r.total_tokens or 0,
            )
            for r in rows
        ]
        return AgentUsersResponse(range=range_str, users=users, limit=limit)
