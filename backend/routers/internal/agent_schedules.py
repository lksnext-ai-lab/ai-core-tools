from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from lks_idprovider.models.auth import AuthContext
from sqlalchemy.orm import Session

from db.database import get_db
from schemas.agent_schedule_schemas import (
    AgentRunSummaryListSchema,
    AgentScheduleCreateSchema,
    AgentScheduleResponseSchema,
    AgentScheduleUpdateSchema,
)
from services.agent_scheduler_service import AgentSchedulerService
from routers.internal.auth_utils import get_current_user_oauth


schedules_router = APIRouter()


def _service(db: Session) -> AgentSchedulerService:
    from scheduling.periodic_agent_task import DBOS, DBOSOrchestrator

    return AgentSchedulerService(db, DBOSOrchestrator() if DBOS is not None else None)


@schedules_router.post("/", response_model=AgentScheduleResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    app_id: int,
    agent_id: int,
    payload: AgentScheduleCreateSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return _service(db).create_schedule(
            agent_id=agent_id, app_id=app_id, created_by=int(auth_context.identity.id),
            cron_expression=payload.cron_expression, timezone_name=payload.timezone,
            input_context=payload.input_context, max_concurrent_runs=payload.max_concurrent_runs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@schedules_router.get("/", response_model=list[AgentScheduleResponseSchema])
async def list_schedules(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return _service(db).list_schedules(agent_id, app_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@schedules_router.patch("/{schedule_id}", response_model=AgentScheduleResponseSchema)
async def update_schedule(
    app_id: int,
    agent_id: int,
    schedule_id: int,
    payload: AgentScheduleUpdateSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return _service(db).update_schedule(schedule_id, agent_id, app_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@schedules_router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    app_id: int,
    agent_id: int,
    schedule_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        _service(db).delete_schedule(schedule_id, agent_id, app_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@schedules_router.get("/{schedule_id}/runs", response_model=AgentRunSummaryListSchema)
async def list_schedule_runs(
    app_id: int,
    agent_id: int,
    schedule_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
):
    try:
        items, total = _service(db).list_runs(schedule_id, agent_id, app_id, page, per_page)
        return AgentRunSummaryListSchema(items=items, page=page, per_page=per_page, total=total)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
