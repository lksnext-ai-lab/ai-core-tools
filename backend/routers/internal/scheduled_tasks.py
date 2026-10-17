import os
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from lks_idprovider.models.auth import AuthContext
from sqlalchemy.orm import Session

from db.database import get_db
from models.scheduled_task import ScheduledTask, ScheduledTaskRun
from routers.controls.role_authorization import AppRole, require_min_role
from routers.internal.auth_utils import get_current_user_oauth
from schemas.scheduled_task_schemas import (
    ScheduledTaskCreateSchema, ScheduledTaskFileDownloadSchema, ScheduledTaskResponseSchema,
    ScheduledTaskRunListSchema, ScheduledTaskRunResponseSchema, ScheduledTaskUpdateSchema,
    ScheduledTaskTriggerResponseSchema,
)
from services.file_management_service import FileManagementService
from services.scheduled_task_service import ScheduledTaskService, default_orchestrator, task_user_context
from utils.security import generate_signature


router = APIRouter(prefix="/apps/{app_id}/scheduled-tasks", tags=["Scheduled tasks"])

Auth = Annotated[AuthContext, Depends(get_current_user_oauth)]
DB = Annotated[Session, Depends(get_db)]
CanView = Annotated[AppRole, Depends(require_min_role("viewer"))]
CanEdit = Annotated[AppRole, Depends(require_min_role("editor"))]


def _service(db: Session) -> ScheduledTaskService:
    # Only hand out the orchestrator once DBOS has actually launched: calling DBOS
    # before that fails with "No DBOS was created yet" (a 500 instead of a clear 400).
    return ScheduledTaskService(db, default_orchestrator())


def _task_or_404(db: Session, task_id: int, app_id: int) -> ScheduledTask:
    try:
        return _service(db).get(task_id, app_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def run_file_download(
    task: ScheduledTask, run: ScheduledTaskRun, file_id: str, request: Request, auth: AuthContext,
) -> ScheduledTaskFileDownloadSchema:
    """Signed /static URL for a file produced by a run (only files recorded on that run)."""
    if not run.conversation_id or not any(f.get("file_id") == file_id for f in run.output_files or []):
        raise HTTPException(status_code=404, detail="File not found")
    files = await FileManagementService().list_attached_files(
        agent_id=task.agent_id, user_context=task_user_context(task), conversation_id=str(run.conversation_id),
    )
    file_data = next((f for f in files if f.get("file_id") == file_id), None)
    if not file_data or not file_data.get("file_path"):
        raise HTTPException(status_code=404, detail="File not found")

    file_path = file_data["file_path"].lstrip("/")
    filename = file_data.get("filename") or os.path.basename(file_path)
    email = auth.identity.email
    base_url = os.getenv("AICT_BASE_URL", "").rstrip("/") or str(request.base_url).rstrip("/")
    signature = generate_signature(file_path, email)
    return ScheduledTaskFileDownloadSchema(
        download_url=f"{base_url}/static/{file_path}?user={email}&sig={signature}&filename={filename}",
        filename=filename,
    )


@router.post("", response_model=ScheduledTaskResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_task(payload: ScheduledTaskCreateSchema, app_id: int, auth: Auth, role: CanEdit, db: DB):
    try:
        return _service(db).create(
            app_id=app_id, created_by=int(auth.identity.id), data=payload.model_dump(),
            output_bindings=payload.output_bindings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[ScheduledTaskResponseSchema])
async def list_tasks(app_id: int, role: CanView, db: DB, agent_id: Optional[int] = None):
    return _service(db).list(app_id, agent_id)


@router.get("/{task_id}", response_model=ScheduledTaskResponseSchema)
async def get_task(task_id: int, app_id: int, role: CanView, db: DB):
    return _task_or_404(db, task_id, app_id)


@router.patch("/{task_id}", response_model=ScheduledTaskResponseSchema)
async def update_task(task_id: int, payload: ScheduledTaskUpdateSchema, app_id: int, role: CanEdit, db: DB):
    _task_or_404(db, task_id, app_id)
    service = _service(db)
    try:
        task = service.update(task_id, app_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.max_runs_retained is not None:
        await service.prune_runs(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, app_id: int, role: CanEdit, db: DB):
    try:
        await _service(db).delete(task_id, app_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{task_id}/runs", response_model=ScheduledTaskRunListSchema)
async def list_task_runs(
    task_id: int, app_id: int, role: CanView, db: DB,
    page: Annotated[int, Query(ge=1)] = 1, per_page: Annotated[int, Query(ge=1, le=200)] = 50,
):
    task = _task_or_404(db, task_id, app_id)
    items, total = _service(db).runs_of(task, page, per_page)
    return ScheduledTaskRunListSchema(items=items, page=page, per_page=per_page, total=total)


@router.get("/{task_id}/runs/{run_id}", response_model=ScheduledTaskRunResponseSchema)
async def get_task_run(task_id: int, run_id: int, app_id: int, role: CanView, db: DB):
    task = _task_or_404(db, task_id, app_id)
    try:
        return _service(db).run_of(task, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{task_id}/runs/{run_id}/files/{file_id}/download", response_model=ScheduledTaskFileDownloadSchema)
async def download_run_file(
    task_id: int, run_id: int, file_id: str, app_id: int, request: Request, auth: Auth, role: CanView, db: DB,
):
    task = _task_or_404(db, task_id, app_id)
    try:
        run = _service(db).run_of(task, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await run_file_download(task, run, file_id, request, auth)


@router.post("/{task_id}/run-now", response_model=ScheduledTaskTriggerResponseSchema, status_code=status.HTTP_202_ACCEPTED)
async def run_task_now(task_id: int, app_id: int, role: CanEdit, db: DB):
    try:
        workflow_id = _service(db).run_now(task_id, app_id)
        return ScheduledTaskTriggerResponseSchema(task_id=task_id, workflow_id=workflow_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
