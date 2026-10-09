import json
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from lks_idprovider import AuthContext
from pydantic import ValidationError
from sqlalchemy.orm import Session

from db.database import get_db
from routers.controls.role_authorization import require_min_role, AppRole
from schemas.middleware_schemas import (
    CreateUpdateMiddlewareSchema,
    MiddlewareDetailSchema,
    MiddlewareListItemSchema,
)
from schemas.export_schemas import MiddlewareExportFileSchema
from schemas.import_schemas import ConflictMode, ImportResponseSchema
from services.middleware_export_service import MiddlewareExportService
from services.middleware_import_service import MiddlewareImportService
from services.middleware_service import MiddlewareService, MiddlewareValidationError
from utils.logger import get_logger
from utils.schema_utils import sanitize_identifier
from .auth_utils import get_current_user_oauth

logger = get_logger(__name__)

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


@middlewares_router.post("/import",
                         summary="Import middleware",
                         tags=["Middlewares", "Export/Import"],
                         response_model=ImportResponseSchema,
                         status_code=status.HTTP_201_CREATED)
async def import_middleware(
    app_id: int,
    file: Annotated[UploadFile, File(...)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    conflict_mode: Annotated[ConflictMode, Query()] = ConflictMode.FAIL,
    new_name: Annotated[Optional[str], Query(max_length=100)] = None,
):
    """Import a middleware from its JSON export file."""
    try:
        export_data = MiddlewareExportFileSchema(**json.loads(await file.read()))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON file")
    except ValidationError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is not a middleware export")
    try:
        summary = MiddlewareImportService(db).import_middleware(export_data, app_id, conflict_mode, new_name)
    except ValueError as e:
        logger.warning(f"Middleware import failed: {e}")
        code = status.HTTP_409_CONFLICT if "already exists" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(code, str(e))
    return ImportResponseSchema(
        success=True,
        message=f"Middleware '{summary.component_name}' imported successfully",
        summary=summary,
    )


@middlewares_router.post("/{middleware_id}/export",
                         summary="Export middleware",
                         tags=["Middlewares", "Export/Import"])
async def export_middleware(
    app_id: int,
    middleware_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """Export a middleware to a JSON file (AI services travel by name)."""
    try:
        export_data = MiddlewareExportService(db).export_middleware(
            middleware_id, app_id, getattr(auth_context, "user_id", None)
        )
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MIDDLEWARE_NOT_FOUND_ERROR)
    filename = f"{sanitize_identifier(export_data.middleware.name)}_middleware.json"
    return JSONResponse(
        content=export_data.model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
