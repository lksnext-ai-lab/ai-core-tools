from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

from db.database import get_db
from routers.controls.role_authorization import require_min_role, AppRole
from schemas.middleware_schemas import (
    CreateUpdateMiddlewareSchema,
    MiddlewareDetailSchema,
    MiddlewareListItemSchema,
)
from services.middleware_service import MiddlewareService, MiddlewareValidationError
from .auth_utils import get_current_user_oauth

MIDDLEWARE_NOT_FOUND_ERROR = "Middleware not found"

middlewares_router = APIRouter()


@middlewares_router.get("/",
                        summary="List middlewares",
                        tags=["Middlewares"],
                        response_model=List[MiddlewareListItemSchema])
async def list_middlewares(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """List all middlewares of an app."""
    return MiddlewareService.list_middlewares(db, app_id)


@middlewares_router.get("/{middleware_id}",
                        summary="Get middleware details",
                        tags=["Middlewares"],
                        response_model=MiddlewareDetailSchema)
async def get_middleware(
    app_id: int,
    middleware_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """Get one middleware of the app."""
    detail = MiddlewareService.get_middleware_detail(db, app_id, middleware_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MIDDLEWARE_NOT_FOUND_ERROR)
    return detail


@middlewares_router.post("/{middleware_id}",
                         summary="Create or update middleware",
                         tags=["Middlewares"],
                         response_model=MiddlewareDetailSchema)
async def create_or_update_middleware(
    app_id: int,
    middleware_id: int,
    data: CreateUpdateMiddlewareSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """Create (``middleware_id`` = 0) or update a middleware."""
    try:
        detail = MiddlewareService.create_or_update_middleware(db, app_id, middleware_id, data)
    except MiddlewareValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MIDDLEWARE_NOT_FOUND_ERROR)
    return detail


@middlewares_router.delete("/{middleware_id}",
                           summary="Delete middleware",
                           tags=["Middlewares"])
async def delete_middleware(
    app_id: int,
    middleware_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """Delete a middleware (it is detached from every agent using it)."""
    if not MiddlewareService.delete_middleware(db, app_id, middleware_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MIDDLEWARE_NOT_FOUND_ERROR)
    return {"message": "Middleware deleted successfully"}
