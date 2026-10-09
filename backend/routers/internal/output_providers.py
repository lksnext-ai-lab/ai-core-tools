"""Application-scoped output destination and scheduled-task delivery API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from lks_idprovider.models.auth import AuthContext
from sqlalchemy.orm import Session

from db.database import get_db
from models.output_delivery import OutputDelivery, OutputDestination
from models.scheduled_task import ScheduledTask
from routers.controls.role_authorization import AppRole, require_min_role
from routers.internal.auth_utils import get_current_user_oauth
from schemas.output_provider_schemas import (
    OutputBindingsResponseSchema,
    OutputDeliveryListResponseSchema,
    OutputDeliveryRetryResponseSchema,
    OutputDestinationCreateSchema,
    OutputDestinationResponseSchema,
    OutputDestinationTestResponseSchema,
    OutputDestinationUpdateSchema,
    OutputProviderDescriptorSchema,
    ScheduledTaskOutputBindingsRequestSchema,
)
from output.service import create_destination, destination_dto, get_destination, request_retry, task_bindings, test_destination, update_destination, replace_task_bindings, delivery_dto
from output.registry import list_output_providers as registered_output_providers
from scheduling.output_delivery import enqueue_delivery

router = APIRouter(prefix="/apps/{app_id}", tags=["Scheduled task output providers"])
Auth = Annotated[AuthContext, Depends(get_current_user_oauth)]
DB = Annotated[Session, Depends(get_db)]
CanView = Annotated[AppRole, Depends(require_min_role("viewer"))]
CanEdit = Annotated[AppRole, Depends(require_min_role("editor"))]


def _task(db: Session, app_id: int, task_id: int) -> ScheduledTask:
    task = db.query(ScheduledTask).filter_by(id=task_id, app_id=app_id).one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return task


def _delivery(db: Session, *, app_id: int, task_id: int, run_id: int, delivery_id: int) -> OutputDelivery:
    delivery = db.query(OutputDelivery).join(OutputDelivery.run).join(ScheduledTask).filter(
        OutputDelivery.id == delivery_id,
        ScheduledTask.app_id == app_id,
        ScheduledTask.id == task_id,
        OutputDelivery.run_id == run_id,
    ).one_or_none()
    if not delivery:
        raise HTTPException(status_code=404, detail="Output delivery not found")
    return delivery


@router.get("/output-providers", response_model=list[OutputProviderDescriptorSchema])
async def list_output_providers(app_id: int, role: CanView):
    return [{"key": provider.descriptor.key, "name": provider.descriptor.name,
             "supports_links": provider.descriptor.supports_links,
             "supports_native_attachments": provider.descriptor.supports_native_attachments,
             "supports_binary_attachments": provider.descriptor.supports_binary_attachments,
             "content_modes": list(provider.descriptor.content_modes)} for provider in registered_output_providers()]


@router.get("/output-destinations", response_model=list[OutputDestinationResponseSchema])
async def list_output_destinations(app_id: int, role: CanView, db: DB):
    items = db.query(OutputDestination).filter_by(app_id=app_id, enabled=True).order_by(OutputDestination.name).all()
    return [destination_dto(item) for item in items]


@router.post("/output-destinations", response_model=OutputDestinationResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_output_destination(app_id: int, payload: OutputDestinationCreateSchema, auth: Auth, role: CanEdit, db: DB):
    try:
        item = create_destination(db, app_id=app_id, created_by=int(auth.identity.id), name=payload.name,
                                  webhook_url=payload.webhook_url, provider_key=payload.provider_key,
                                  content_mode=payload.content_mode,
                                  public_config=payload.public_config, credentials=payload.credentials)
        return destination_dto(item)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/output-destinations/{destination_id}", response_model=OutputDestinationResponseSchema)
async def patch_output_destination(app_id: int, destination_id: int, payload: OutputDestinationUpdateSchema, role: CanEdit, db: DB):
    try:
        item = get_destination(db, app_id=app_id, destination_id=destination_id)
        return destination_dto(update_destination(db, item, payload.model_dump(exclude_unset=True)))
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc


@router.delete("/output-destinations/{destination_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_output_destination(app_id: int, destination_id: int, role: CanEdit, db: DB):
    try:
        item = get_destination(db, app_id=app_id, destination_id=destination_id)
        if item.bindings:
            # Keep delivery history but remove this destination from every task.
            item.enabled = False
            for binding in item.bindings:
                binding.enabled = False
            db.query(OutputDelivery).filter(
                OutputDelivery.destination_id == destination_id,
                OutputDelivery.status.in_(["pending", "retry_wait"]),
            ).update({OutputDelivery.status: "cancelled"}, synchronize_session=False)
        else:
            db.delete(item)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/output-destinations/{destination_id}/test", response_model=OutputDestinationTestResponseSchema)
async def test_output_destination(app_id: int, destination_id: int, role: CanEdit, db: DB):
    try:
        item = get_destination(db, app_id=app_id, destination_id=destination_id)
        receipt = await test_destination(item)
        return {"accepted": True, **receipt}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/scheduled-tasks/{task_id}/outputs", response_model=OutputBindingsResponseSchema)
async def get_task_outputs(app_id: int, task_id: int, role: CanView, db: DB):
    task = _task(db, app_id, task_id)
    return {"bindings": task_bindings(db, task=task, app_id=app_id)}


@router.put("/scheduled-tasks/{task_id}/outputs", response_model=OutputBindingsResponseSchema)
async def put_task_outputs(app_id: int, task_id: int, payload: ScheduledTaskOutputBindingsRequestSchema, role: CanEdit, db: DB):
    task = _task(db, app_id, task_id)
    try:
        bindings = replace_task_bindings(
            db, task=task, app_id=app_id,
            bindings=[item.model_dump(exclude={"destination_name"}) for item in payload.bindings],
        )
        return {"bindings": bindings}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/scheduled-tasks/{task_id}/runs/{run_id}/deliveries", response_model=OutputDeliveryListResponseSchema)
async def list_run_deliveries(app_id: int, task_id: int, run_id: int, role: CanView, db: DB):
    task = _task(db, app_id, task_id)
    run = next((item for item in task.runs if item.id == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="Scheduled task run not found")
    items = db.query(OutputDelivery).filter_by(run_id=run_id).order_by(OutputDelivery.id).all()
    return {"deliveries": [delivery_dto(item) for item in items]}


@router.post("/scheduled-tasks/{task_id}/runs/{run_id}/deliveries/{delivery_id}/retry", response_model=OutputDeliveryRetryResponseSchema, status_code=status.HTTP_202_ACCEPTED)
async def retry_run_delivery(app_id: int, task_id: int, run_id: int, delivery_id: int, role: CanEdit, db: DB):
    item = _delivery(db, app_id=app_id, task_id=task_id, run_id=run_id, delivery_id=delivery_id)
    try:
        request_retry(db, item)
        workflow_id = enqueue_delivery(item.id, item.dispatch_generation)
        return {"delivery_id": item.id, "status": "queued", "workflow_id": workflow_id}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
