from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from lks_idprovider.models.auth import AuthContext
from sqlalchemy.orm import Session

from db.database import get_db
from routers.internal.auth_utils import get_current_user_oauth
from schemas.scheduled_task_schemas import (
    ScheduledTaskCreateSchema, ScheduledTaskResponseSchema, ScheduledTaskRunListSchema,
    ScheduledTaskRunResponseSchema, ScheduledTaskUpdateSchema,
    ScheduledTaskTriggerResponseSchema,
)
from services.scheduled_task_service import ScheduledTaskService
from models.scheduled_task import ScheduledTaskRun


router = APIRouter(prefix="/scheduled-tasks", tags=["Scheduled tasks"])


def _service(db: Session) -> ScheduledTaskService:
    from scheduling.periodic_agent_task import DBOS, DBOSOrchestrator
    return ScheduledTaskService(db, DBOSOrchestrator() if DBOS is not None else None)


@router.post("", response_model=ScheduledTaskResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_task(payload: ScheduledTaskCreateSchema, app_id: int, auth: Annotated[AuthContext, Depends(get_current_user_oauth)], db: Annotated[Session, Depends(get_db)]):
    try:
        return _service(db).create(app_id=app_id, created_by=int(auth.identity.id), data=payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[ScheduledTaskResponseSchema])
async def list_tasks(app_id: int, auth: Annotated[AuthContext, Depends(get_current_user_oauth)], db: Annotated[Session, Depends(get_db)], agent_id: Optional[int] = None):
    return _service(db).list(app_id, agent_id)


@router.patch("/{task_id}", response_model=ScheduledTaskResponseSchema)
async def update_task(task_id: int, payload: ScheduledTaskUpdateSchema, app_id: int, auth: Annotated[AuthContext, Depends(get_current_user_oauth)], db: Annotated[Session, Depends(get_db)]):
    try:
        return _service(db).update(task_id, app_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, app_id: int, auth: Annotated[AuthContext, Depends(get_current_user_oauth)], db: Annotated[Session, Depends(get_db)]):
    try:
        _service(db).delete(task_id, app_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{task_id}/runs", response_model=ScheduledTaskRunListSchema)
async def list_task_runs(task_id: int, app_id: int, auth: Annotated[AuthContext, Depends(get_current_user_oauth)], db: Annotated[Session, Depends(get_db)], page: Annotated[int, Query(ge=1)] = 1, per_page: Annotated[int, Query(ge=1, le=200)] = 50):
    try:
        items, total = _service(db).runs(task_id, app_id, page, per_page)
        return ScheduledTaskRunListSchema(items=items, page=page, per_page=per_page, total=total)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{task_id}/runs/{run_id}", response_model=ScheduledTaskRunResponseSchema)
async def get_task_run(task_id: int, run_id: int, app_id: int, auth: Annotated[AuthContext, Depends(get_current_user_oauth)], db: Annotated[Session, Depends(get_db)]):
    task = _service(db)._task(task_id, app_id)
    run = db.query(ScheduledTaskRun).filter_by(id=run_id, scheduled_task_id=task.id).one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Scheduled task run not found")
    return run


@router.post("/{task_id}/run-now", response_model=ScheduledTaskTriggerResponseSchema, status_code=status.HTTP_202_ACCEPTED)
async def run_task_now(task_id: int, app_id: int, auth: Annotated[AuthContext, Depends(get_current_user_oauth)], db: Annotated[Session, Depends(get_db)]):
    try:
        workflow_id = _service(db).run_now(task_id, app_id)
        return ScheduledTaskTriggerResponseSchema(task_id=task_id, workflow_id=workflow_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
