from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from typing import Annotated
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from typing import List, Optional
import json

# Import database dependency
from db.database import get_db

# Import services
from services.sandbox_service_service import SandboxServiceService

# Import schemas and auth
from schemas.sandbox_service_schemas import (
    SandboxServiceListItemSchema,
    SandboxServiceDetailSchema,
    CreateUpdateSandboxServiceSchema,
)
from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole
from tools.sandbox.factory import SandboxProviderUnavailableError

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)


sandbox_services_router = APIRouter()

SANDBOX_SERVICE_NOT_FOUND_ERROR = "Sandbox service not found"

# SANDBOX SERVICE MANAGEMENT

@sandbox_services_router.get("/",
                             summary="List sandbox services",
                             tags=["Sandbox Services"],
                             response_model=List[SandboxServiceListItemSchema])
async def list_sandbox_services(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    db: Annotated[Session, Depends(get_db)]
):
    """
    List all sandbox services for a specific app.
    """

    try:
        return SandboxServiceService.get_sandbox_services_by_app_id(db, app_id)
    except Exception as e:
        logger.error("Error retrieving sandbox services (app_id: %s): %s", app_id, type(e).__name__, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving sandbox services"
        )


# ==================== STATIC ROUTES (must come before /{service_id}) ====================


@sandbox_services_router.post("/test-connection",
                              summary="Test sandbox service connection with config",
                              tags=["Sandbox Services"])
async def test_sandbox_service_connection_with_config(
    app_id: int,
    config: CreateUpdateSandboxServiceSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    service_id: Optional[int] = Query(None, description="Edit-mode: recover stored API key when the request sends a masked placeholder"),
):
    """
    Test connection to a sandbox service using provided configuration.

    When ``service_id`` is supplied and ``api_key`` is empty/masked, the
    persisted key for that service is used. This lets the UI run a test
    without forcing the user to re-type the secret on every check.
    """
    from utils.secret_utils import is_masked_key
    from core.export_constants import PLACEHOLDER_API_KEY
    from repositories.sandbox_service_repository import SandboxServiceRepository
    from tools.sandbox_service_utils import build_extra_config

    try:
        # If user sent a masked placeholder, fall back to the stored key.
        api_key = config.api_key or ""
        if service_id is not None and (
            not api_key
            or api_key == PLACEHOLDER_API_KEY
            or is_masked_key(api_key)
        ):
            stored = SandboxServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
            if stored and stored.api_key:
                api_key = stored.api_key

        service_config = {
            "provider": config.provider,
            "api_key": api_key,
            "endpoint": config.base_url,
            "extra_config": build_extra_config(
                config.provider,
                image=config.opensandbox_image,
                target=config.daytona_target,
                workspace=config.daytona_workspace or config.e2b_workspace,
                cpu=config.daytona_cpu,
                memory_gb=config.daytona_memory_gb,
                template=config.e2b_template,
            ),
        }
        result = SandboxServiceService.test_connection_with_config(service_config)

        # Ensure we don't leak sensitive information in successful responses
        if isinstance(result, dict) and 'response' in result:
            if len(str(result.get('response', ''))) > 500:
                result['response'] = str(result['response'])[:500] + '... (truncated)'

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error testing sandbox service connection (provider: %s): %s",
            config.provider,
            type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error testing sandbox service connection"
        )


@sandbox_services_router.post(
    "/import",
    summary="Import Sandbox Service",
    tags=["Sandbox Services", "Export/Import"],
    status_code=status.HTTP_201_CREATED
)
async def import_sandbox_service(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
):
    """Import a Sandbox Service from a JSON export file.

    The export/import service layer for SandboxService is not yet
    implemented (a follow-up task); this endpoint accepts the same file
    shape as a placeholder for API-surface parity with AI/Embedding
    Services and returns 501 until that layer exists.
    """
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Sandbox Service import is not yet implemented",
    )


# ==================== DYNAMIC ROUTES (with {service_id} parameter) ====================


@sandbox_services_router.get("/{service_id}",
                             summary="Get sandbox service details",
                             tags=["Sandbox Services"],
                             response_model=SandboxServiceDetailSchema)
async def get_sandbox_service(
    app_id: int,
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    db: Annotated[Session, Depends(get_db)]
):
    """
    Get detailed information about a specific sandbox service.
    """

    try:
        result = SandboxServiceService.get_sandbox_service_detail(db, app_id, service_id)
        if result is None and service_id != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SANDBOX_SERVICE_NOT_FOUND_ERROR
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error retrieving sandbox service (service_id: %s): %s", service_id, type(e).__name__, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving sandbox service"
        )


@sandbox_services_router.post("/{service_id}",
                              summary="Create or update sandbox service",
                              tags=["Sandbox Services"],
                              response_model=SandboxServiceDetailSchema)
async def create_or_update_sandbox_service(
    app_id: int,
    service_id: int,
    service_data: CreateUpdateSandboxServiceSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    db: Annotated[Session, Depends(get_db)]
):
    """
    Create a new sandbox service or update an existing one.
    """

    try:
        result = SandboxServiceService.create_or_update_sandbox_service(db, app_id, service_id, service_data)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SANDBOX_SERVICE_NOT_FOUND_ERROR
            )
        return result
    except HTTPException:
        raise
    except SandboxProviderUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(
            "Error creating/updating sandbox service (service_id: %s): %s",
            service_id,
            type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating/updating sandbox service"
        )


@sandbox_services_router.post("/{service_id}/copy",
                              summary="Copy sandbox service",
                              tags=["Sandbox Services"],
                              response_model=SandboxServiceDetailSchema)
async def copy_sandbox_service(
    app_id: int,
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    db: Annotated[Session, Depends(get_db)]
):
    """
    Copy an existing sandbox service.
    """
    try:
        result = SandboxServiceService.copy_sandbox_service(db, app_id, service_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SANDBOX_SERVICE_NOT_FOUND_ERROR
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error copying sandbox service (service_id: %s): %s", service_id, type(e).__name__, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error copying sandbox service"
        )


@sandbox_services_router.delete("/{service_id}",
                                summary="Delete sandbox service",
                                tags=["Sandbox Services"])
async def delete_sandbox_service(
    app_id: int,
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    db: Annotated[Session, Depends(get_db)]
):
    """
    Delete a sandbox service.
    """

    try:
        success = SandboxServiceService.delete_sandbox_service(db, app_id, service_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SANDBOX_SERVICE_NOT_FOUND_ERROR
            )

        return {"message": "Sandbox service deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error deleting sandbox service (service_id: %s): %s", service_id, type(e).__name__, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting sandbox service"
        )


@sandbox_services_router.post("/{service_id}/test",
                              summary="Test sandbox service connection",
                              tags=["Sandbox Services"])
async def test_sandbox_service_connection(
    app_id: int,
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    db: Annotated[Session, Depends(get_db)]
):
    """
    Test connection to sandbox service.
    """
    try:
        return SandboxServiceService.test_connection(db, app_id, service_id)
    except Exception as e:
        logger.error(
            "Error testing sandbox service connection (service_id: %s): %s",
            service_id,
            type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error testing sandbox service connection"
        )


# ==================== EXPORT/IMPORT ENDPOINTS ====================


@sandbox_services_router.post(
    "/{service_id}/export",
    summary="Export Sandbox Service",
    tags=["Sandbox Services", "Export/Import"],
    status_code=status.HTTP_200_OK
)
async def export_sandbox_service(
    app_id: int,
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    db: Annotated[Session, Depends(get_db)]
):
    """Export Sandbox Service configuration to JSON file.

    The export/import service layer for SandboxService is not yet
    implemented (a follow-up task); this endpoint is a placeholder for
    API-surface parity with AI/Embedding Services and returns 501 until
    that layer exists.
    """
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Sandbox Service export is not yet implemented",
    )
