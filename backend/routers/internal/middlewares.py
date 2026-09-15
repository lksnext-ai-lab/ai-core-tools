from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Annotated
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

from schemas.middleware_schemas import MiddlewareListItemSchema, MiddlewareDetailSchema, CreateUpdateMiddlewareSchema
from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole

from db.database import get_db
from services.middleware_service import MiddlewareService

from utils.logger import get_logger

MIDDLEWARE_NOT_FOUND_ERROR = "Middleware not found"

logger = get_logger(__name__)

middlewares_router = APIRouter()

# ==================== MIDDLEWARE MANAGEMENT ====================


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
    """List all middlewares for a specific app."""
    try:
        return MiddlewareService.list_middlewares(db, app_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving middlewares: {str(e)}"
        )


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
    """Get detailed information about a specific middleware."""
    try:
        detail = MiddlewareService.get_middleware_detail(db, app_id, middleware_id)

        if detail is None and middleware_id != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=MIDDLEWARE_NOT_FOUND_ERROR
            )

        return detail

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving middleware: {str(e)}"
        )


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
    """Create a new middleware or update an existing one."""
    try:
        middleware = MiddlewareService.create_or_update_middleware(db, app_id, middleware_id, data)

        if middleware is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=MIDDLEWARE_NOT_FOUND_ERROR
            )

        return await get_middleware(app_id, middleware.middleware_id, auth_context, db, role)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating middleware: {str(e)}"
        )


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
    """Delete a middleware."""
    try:
        success = MiddlewareService.delete_middleware(db, app_id, middleware_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=MIDDLEWARE_NOT_FOUND_ERROR
            )

        return {"message": "Middleware deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting middleware: {str(e)}"
        )
