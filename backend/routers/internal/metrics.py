"""Agent metrics dashboard endpoints (mounted under /internal).

Three scopes share the same queries and response shapes:
  - system:  /admin/metrics/...                          (platform admins)
  - app:     /apps/{app_id}/metrics/...                  (app administrators)
  - agent:   /apps/{app_id}/agents/{agent_id}/metrics/... (app editors)
"""

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from lks_idprovider.models.auth import AuthContext
from sqlalchemy.orm import Session

from db.database import get_db
from routers.controls.role_authorization import AppRole, require_min_role
from routers.internal.admin import require_admin
from schemas.metrics_schemas import (
    BreakdownDimension,
    BreakdownResponse,
    ErrorsResponse,
    MetricsRange,
    SummaryResponse,
    TimeseriesResponse,
    ToolsResponse,
)
from services.metrics_query_service import MetricsQueryService, MetricsScope

router = APIRouter(tags=["Metrics"])

RangeParam = Annotated[MetricsRange, Query(description="Time window")]
DbSession = Annotated[Session, Depends(get_db)]

SYSTEM_DIMENSIONS = {"app", "agent", "model", "provider", "channel"}
APP_DIMENSIONS = {"agent", "model", "provider", "channel", "user"}
AGENT_DIMENSIONS = {"model", "channel", "user"}


def _checked(dimension: str, allowed: set[str]) -> str:
    if dimension not in allowed:
        raise HTTPException(status_code=400, detail=f"Breakdown by '{dimension}' is not available here.")
    return dimension


def _register(prefix: str, guard: Callable, scope_of: Callable[..., MetricsScope], dimensions: set[str]) -> None:
    """Register the six metrics endpoints for one scope."""

    @router.get(f"{prefix}/summary", response_model=SummaryResponse)
    async def summary(db: DbSession, scope: Annotated[MetricsScope, Depends(scope_of)],
                      _: Annotated[object, Depends(guard)], range: RangeParam = "7d"):
        return MetricsQueryService.summary(db, scope, range)

    @router.get(f"{prefix}/timeseries", response_model=TimeseriesResponse)
    async def timeseries(db: DbSession, scope: Annotated[MetricsScope, Depends(scope_of)],
                         _: Annotated[object, Depends(guard)], range: RangeParam = "7d"):
        return MetricsQueryService.timeseries(db, scope, range)

    @router.get(f"{prefix}/breakdown/{{dimension}}", response_model=BreakdownResponse)
    async def breakdown(dimension: BreakdownDimension, db: DbSession,
                        scope: Annotated[MetricsScope, Depends(scope_of)],
                        _: Annotated[object, Depends(guard)], range: RangeParam = "7d"):
        return MetricsQueryService.breakdown(db, scope, range, _checked(dimension, dimensions))

    @router.get(f"{prefix}/tools", response_model=ToolsResponse)
    async def tools(db: DbSession, scope: Annotated[MetricsScope, Depends(scope_of)],
                    _: Annotated[object, Depends(guard)], range: RangeParam = "7d"):
        return MetricsQueryService.tools(db, scope, range)

    @router.get(f"{prefix}/errors", response_model=ErrorsResponse)
    async def errors(db: DbSession, scope: Annotated[MetricsScope, Depends(scope_of)],
                     _: Annotated[object, Depends(guard)], range: RangeParam = "7d"):
        return MetricsQueryService.errors(db, scope, range)


def _system_scope() -> MetricsScope:
    return MetricsScope()


def _app_scope(app_id: int) -> MetricsScope:
    return MetricsScope(app_id=app_id)


def _agent_scope(app_id: int, agent_id: int, db: DbSession) -> MetricsScope:
    MetricsQueryService.check_agent_in_app(db, app_id, agent_id)
    return MetricsScope(app_id=app_id, agent_id=agent_id)


def _app_admin(role: Annotated[AppRole, Depends(require_min_role("administrator"))]) -> AppRole:
    return role


def _app_editor(role: Annotated[AppRole, Depends(require_min_role("editor"))]) -> AppRole:
    return role


def _platform_admin(auth: Annotated[AuthContext, Depends(require_admin)]) -> AuthContext:
    return auth


_register("/admin/metrics", _platform_admin, _system_scope, SYSTEM_DIMENSIONS)
_register("/apps/{app_id}/metrics", _app_admin, _app_scope, APP_DIMENSIONS)
_register("/apps/{app_id}/agents/{agent_id}/metrics", _app_editor, _agent_scope, AGENT_DIMENSIONS)
