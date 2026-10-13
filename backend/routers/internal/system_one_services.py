"""System One services of an app (connections to a System One server). Mounted under /{app_id}/system-one-services."""
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

from db.database import get_db
from routers.controls.role_authorization import AppRole, require_min_role
from schemas.system_one_service_schemas import (
    CreateUpdateSystemOneServiceSchema,
    SystemOneConnectionConfigSchema,
    SystemOneServiceDetailSchema,
    SystemOneServiceListItemSchema,
)
from services.system_one_service_service import SystemOneServiceService
from utils.logger import get_logger

from .auth_utils import get_current_user_oauth

logger = get_logger(__name__)

system_one_services_router = APIRouter()

NOT_FOUND = "System One service not found"
TAG = ["System One Services"]


def _server_error(action: str, exc: Exception, **ctx) -> HTTPException:
    # Log only the exception type: the message of an unhandled error may carry credentials.
    logger.error("Error %s (%s): %s", action, ctx, type(exc).__name__)
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error {action}")


@system_one_services_router.get("/", summary="List System One services", tags=TAG,
                                response_model=List[SystemOneServiceListItemSchema])
async def list_system_one_services(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return SystemOneServiceService.get_system_one_services_by_app_id(db, app_id)
    except Exception as exc:
        raise _server_error("retrieving System One services", exc, app_id=app_id)


# Static routes must come before /{service_id}.
@system_one_services_router.post("/test-connection", summary="Test a System One connection with the form values",
                                 tags=TAG)
async def test_system_one_connection_with_config(
    app_id: int,
    config: SystemOneConnectionConfigSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    db: Annotated[Session, Depends(get_db)],
    service_id: Optional[int] = Query(None, description="Edit mode: use the stored token when the form sends a masked one"),
):
    try:
        return await SystemOneServiceService.test_connection_with_config(
            db, app_id, {"endpoint": config.endpoint, "api_key": config.api_key, "model": config.model}, service_id)
    except Exception as exc:
        raise _server_error("testing the System One connection", exc, app_id=app_id)


@system_one_services_router.get("/{service_id}", summary="Get a System One service", tags=TAG,
                                response_model=SystemOneServiceDetailSchema)
async def get_system_one_service(
    app_id: int,
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        result = SystemOneServiceService.get_system_one_service_detail(db, app_id, service_id)
    except Exception as exc:
        raise _server_error("retrieving the System One service", exc, app_id=app_id, service_id=service_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return result


@system_one_services_router.post("/{service_id}", summary="Create or update a System One service", tags=TAG,
                                 response_model=SystemOneServiceDetailSchema)
async def create_or_update_system_one_service(
    app_id: int,
    service_id: int,
    data: CreateUpdateSystemOneServiceSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        result = SystemOneServiceService.create_or_update_system_one_service(db, app_id, service_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise _server_error("saving the System One service", exc, app_id=app_id, service_id=service_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return result


@system_one_services_router.post("/{service_id}/copy", summary="Copy a System One service", tags=TAG,
                                 response_model=SystemOneServiceDetailSchema)
async def copy_system_one_service(
    app_id: int,
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        result = SystemOneServiceService.copy_system_one_service(db, app_id, service_id)
    except Exception as exc:
        raise _server_error("copying the System One service", exc, app_id=app_id, service_id=service_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return result


@system_one_services_router.delete("/{service_id}", summary="Delete a System One service", tags=TAG)
async def delete_system_one_service(
    app_id: int,
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        detached = SystemOneServiceService.delete_system_one_service(db, app_id, service_id)
    except Exception as exc:
        raise _server_error("deleting the System One service", exc, app_id=app_id, service_id=service_id)
    if detached is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return {"message": "System One service deleted successfully", "detached_agents": detached}


@system_one_services_router.get("/{service_id}/status", summary="Is a saved System One service reachable?", tags=TAG)
async def system_one_service_status(
    app_id: int,
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    db: Annotated[Session, Depends(get_db)],
):
    """Reachability and token check for the services table. Never makes the real (token-spending) call and
    returns neither models nor limits."""
    try:
        result = await SystemOneServiceService.test_connection(db, app_id, service_id, live_call=False)
    except Exception as exc:
        raise _server_error("checking the System One service status", exc, app_id=app_id, service_id=service_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return {
        "status": result["status"],
        "message": result["message"],
        # A server with no health or model endpoint cannot be verified without a real call: say so apart from "ok".
        "verifiable": bool(result["models"]) or "no health or model endpoints" not in result["message"],
    }


@system_one_services_router.post("/{service_id}/test", summary="Test a saved System One service", tags=TAG)
async def test_system_one_service(
    app_id: int,
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        result = await SystemOneServiceService.test_connection(db, app_id, service_id)
    except Exception as exc:
        raise _server_error("testing the System One service", exc, app_id=app_id, service_id=service_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return result
