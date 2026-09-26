"""Agent metrics dashboard endpoints (mounted under /internal)."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from lks_idprovider.models.auth import AuthContext
from db.database import get_db
from routers.internal.auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole

from schemas.metrics_schemas import (
    AppSummaryResponse,
    AppExecutionsResponse,
    AppAgentsResponse,
    AppModelsResponse,
    AppUsersResponse,
    AgentSummaryResponse,
    AgentExecutionsResponse,
    AgentTokensResponse,
    AgentErrorsResponse,
    AgentLatencyResponse,
    AgentToolsResponse,
    AgentUsersResponse,
)
from services.metrics_query_service import MetricsQueryService

router = APIRouter(tags=["Metrics"])

VALID_RANGES = {"24h", "7d", "30d"}


def _validate_range(range: str) -> str:
    if range not in VALID_RANGES:
        raise HTTPException(
            status_code=400,
            detail="Invalid range. Use one of: 24h, 7d, 30d.",
        )
    return range


# ── App-level endpoints (require ADMINISTRATOR) ───────────────────────────────

@router.get("/apps/{app_id}/metrics/summary", response_model=AppSummaryResponse)
async def get_app_metrics_summary(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    range: Annotated[str, Query()] = "7d",
):
    _validate_range(range)
    return MetricsQueryService.app_summary(db, app_id, range)


@router.get("/apps/{app_id}/metrics/executions", response_model=AppExecutionsResponse)
async def get_app_metrics_executions(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    range: Annotated[str, Query()] = "7d",
    caller_type: Annotated[Optional[str], Query()] = None,
):
    _validate_range(range)
    return MetricsQueryService.app_executions(db, app_id, range, caller_type)


@router.get("/apps/{app_id}/metrics/agents", response_model=AppAgentsResponse)
async def get_app_metrics_agents(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    range: Annotated[str, Query()] = "7d",
):
    _validate_range(range)
    return MetricsQueryService.app_agents(db, app_id, range)


@router.get("/apps/{app_id}/metrics/models", response_model=AppModelsResponse)
async def get_app_metrics_models(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    range: Annotated[str, Query()] = "7d",
):
    _validate_range(range)
    return MetricsQueryService.app_models(db, app_id, range)


@router.get("/apps/{app_id}/metrics/users", response_model=AppUsersResponse)
async def get_app_metrics_users(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    range: Annotated[str, Query()] = "7d",
):
    _validate_range(range)
    return MetricsQueryService.app_users(db, app_id, range)


# ── Per-agent endpoints (require EDITOR) ─────────────────────────────────────

@router.get(
    "/apps/{app_id}/agents/{agent_id}/metrics/summary",
    response_model=AgentSummaryResponse,
)
async def get_agent_metrics_summary(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
    range: Annotated[str, Query()] = "7d",
):
    _validate_range(range)
    return MetricsQueryService.agent_summary(db, app_id, agent_id, range)


@router.get(
    "/apps/{app_id}/agents/{agent_id}/metrics/executions",
    response_model=AgentExecutionsResponse,
)
async def get_agent_metrics_executions(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
    range: Annotated[str, Query()] = "7d",
):
    _validate_range(range)
    return MetricsQueryService.agent_executions(db, app_id, agent_id, range)


@router.get(
    "/apps/{app_id}/agents/{agent_id}/metrics/tokens",
    response_model=AgentTokensResponse,
)
async def get_agent_metrics_tokens(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
    range: Annotated[str, Query()] = "7d",
):
    _validate_range(range)
    return MetricsQueryService.agent_tokens(db, app_id, agent_id, range)


@router.get(
    "/apps/{app_id}/agents/{agent_id}/metrics/errors",
    response_model=AgentErrorsResponse,
)
async def get_agent_metrics_errors(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
    range: Annotated[str, Query()] = "7d",
):
    _validate_range(range)
    return MetricsQueryService.agent_errors(db, app_id, agent_id, range)


@router.get(
    "/apps/{app_id}/agents/{agent_id}/metrics/latency",
    response_model=AgentLatencyResponse,
)
async def get_agent_metrics_latency(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
    range: Annotated[str, Query()] = "7d",
):
    _validate_range(range)
    return MetricsQueryService.agent_latency(db, app_id, agent_id, range)


@router.get(
    "/apps/{app_id}/agents/{agent_id}/metrics/tools",
    response_model=AgentToolsResponse,
)
async def get_agent_metrics_tools(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
    range: Annotated[str, Query()] = "7d",
):
    _validate_range(range)
    return MetricsQueryService.agent_tools(db, app_id, agent_id, range)


@router.get(
    "/apps/{app_id}/agents/{agent_id}/metrics/users",
    response_model=AgentUsersResponse,
)
async def get_agent_metrics_users(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
    range: Annotated[str, Query()] = "7d",
):
    _validate_range(range)
    return MetricsQueryService.agent_users(db, app_id, agent_id, range)
