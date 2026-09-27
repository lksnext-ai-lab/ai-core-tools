"""Marketplace: read-only results of published scheduled tasks."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from lks_idprovider.models.auth import AuthContext
from sqlalchemy.orm import Session

from db.database import get_db
from models.scheduled_task import ScheduledTask
from routers.internal.auth_utils import get_current_user_oauth
from routers.internal.scheduled_tasks import run_file_download
from schemas.scheduled_task_schemas import (
    MarketplaceScheduledTaskCardSchema, MarketplaceScheduledTaskCatalogSchema,
    ScheduledTaskFileDownloadSchema, ScheduledTaskRunListSchema, ScheduledTaskRunResponseSchema,
)
from services.scheduled_task_marketplace_service import ScheduledTaskMarketplaceService
from services.scheduled_task_service import ScheduledTaskService

router = APIRouter(prefix="/marketplace/scheduled-tasks", tags=["Marketplace"])

Auth = Annotated[AuthContext, Depends(get_current_user_oauth)]
DB = Annotated[Session, Depends(get_db)]
TASK_NOT_FOUND = "Scheduled task not found"


def _market(db: Session, auth: AuthContext) -> ScheduledTaskMarketplaceService:
    return ScheduledTaskMarketplaceService(db, int(auth.identity.id))


def _visible_task(db: Session, auth: AuthContext, task_id: int) -> ScheduledTask:
    task = _market(db, auth).get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND)
    return task


@router.get("", response_model=MarketplaceScheduledTaskCatalogSchema)
async def list_marketplace_tasks(
    auth: Auth, db: DB,
    search: Optional[str] = Query(default=None, max_length=200),
    my_apps_only: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 12,
):
    return _market(db, auth).catalog(search=search, my_apps_only=my_apps_only, page=page, page_size=page_size)


@router.get("/{task_id}", response_model=MarketplaceScheduledTaskCardSchema)
async def get_marketplace_task(task_id: int, auth: Auth, db: DB):
    task = _visible_task(db, auth, task_id)
    return _market(db, auth).card(task)


@router.get("/{task_id}/runs", response_model=ScheduledTaskRunListSchema)
async def list_marketplace_task_runs(
    task_id: int, auth: Auth, db: DB,
    page: Annotated[int, Query(ge=1)] = 1, per_page: Annotated[int, Query(ge=1, le=200)] = 50,
):
    task = _visible_task(db, auth, task_id)
    items, total = ScheduledTaskService(db).runs_of(task, page, per_page)
    return ScheduledTaskRunListSchema(items=items, page=page, per_page=per_page, total=total)


@router.get("/{task_id}/runs/{run_id}", response_model=ScheduledTaskRunResponseSchema)
async def get_marketplace_task_run(task_id: int, run_id: int, auth: Auth, db: DB):
    task = _visible_task(db, auth, task_id)
    try:
        return ScheduledTaskService(db).run_of(task, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{task_id}/runs/{run_id}/files/{file_id}/download", response_model=ScheduledTaskFileDownloadSchema)
async def download_marketplace_run_file(task_id: int, run_id: int, file_id: str, request: Request, auth: Auth, db: DB):
    task = _visible_task(db, auth, task_id)
    try:
        run = ScheduledTaskService(db).run_of(task, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await run_file_download(task, run, file_id, request, auth)
