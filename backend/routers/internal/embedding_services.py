from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import JSONResponse
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from typing import List, Optional, Annotated
import json

# Import schemas and auth
from schemas.embedding_service_schemas import (
    EmbeddingServiceListItemSchema,
    EmbeddingServiceDetailSchema,
    CreateUpdateEmbeddingServiceSchema
)
from schemas.import_schemas import ConflictMode, ImportResponseSchema
from schemas.export_schemas import EmbeddingServiceExportFileSchema
from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole

# Import database dependency
from db.database import get_db

# Import services
from services.embedding_service_service import EmbeddingServiceService
from services.embedding_service_export_service import EmbeddingServiceExportService
from services.embedding_service_import_service import EmbeddingServiceImportService
from services.provider_models_service import (
    PROVIDER_ERROR_STATUS,
    ProviderModelsService,
)

from schemas.provider_models_schemas import (
    ListProviderModelsRequest,
    ListProviderModelsResponse,
)
from tools.ai.provider_model_clients import ProviderListingError

# Import logger
from utils.logger import get_logger


logger = get_logger(__name__)

EMBEDDING_SERVICE_NOT_FOUND_MSG = "Embedding service not found"

embedding_services_router = APIRouter()

#EMBEDDING SERVICE MANAGEMENT

@embedding_services_router.get("/", 
                               summary="List embedding services",
                               tags=["Embedding Services"],
                               response_model=List[EmbeddingServiceListItemSchema])
async def list_embedding_services(
    app_id: int,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """
    List all embedding services for a specific app.
    """
    
    try:
        return EmbeddingServiceService.get_embedding_services_list(db, app_id)
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving embedding services: {str(e)}"
        )


# ==================== STATIC ROUTES (without {service_id} parameter) ====================


@embedding_services_router.post(
    "/list-models",
    summary="List embedding models available from a provider",
    tags=["Embedding Services"],
    response_model=ListProviderModelsResponse,
)
async def list_embedding_service_provider_models(
    body: ListProviderModelsRequest,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """List embedding models for the given provider using the credentials
    in the request body. Credentials are NOT persisted.
    """
    body.purpose = "embedding"  # forced server-side
    try:
        return ProviderModelsService.list_models(body)
    except ProviderListingError as exc:
        status_code = PROVIDER_ERROR_STATUS.get(exc.code, 500)
        raise HTTPException(status_code=status_code, detail=exc.message)
    except Exception as e:
        # Log only the exception type — see the AI services router for the
        # rationale (avoid leaking credentials embedded in SDK errors).
        logger.error(
            "Unexpected error listing embedding models (provider: %s): %s",
            body.provider,
            type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list provider models",
        )


@embedding_services_router.post(
    "/test-connection",
    summary="Test embedding service connection with config",
    tags=["Embedding Services"],
)
async def test_embedding_service_connection_with_config(
    config: CreateUpdateEmbeddingServiceSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """Test connection to an embedding service using provided configuration."""
    try:
        service_config = {
            "provider": config.provider,
            "description": config.model_name,
            "api_key": config.api_key,
            "endpoint": config.base_url,
        }
        result = EmbeddingServiceService.test_connection_with_config(service_config)
        return result
    except HTTPException:
        raise
    except Exception as e:
        # Avoid str(e) — SDK errors sometimes include the API key.
        logger.error(
            "Error testing embedding service connection (provider: %s): %s",
            config.provider,
            type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error testing embedding service connection",
        )


@embedding_services_router.post(
    "/import",
    summary="Import Embedding Service",
    tags=["Embedding Services", "Export/Import"],
    response_model=ImportResponseSchema,
    status_code=status.HTTP_201_CREATED
)
async def import_embedding_service(
    app_id: int,
    file: Annotated[UploadFile, File(...)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    conflict_mode: Annotated[ConflictMode, Query()] = ConflictMode.FAIL,
    new_name: Annotated[Optional[str], Query()] = None,
):
    """Import Embedding Service from JSON file."""
    try:
        # Parse file
        content = await file.read()
        file_data = json.loads(content)
        export_data = EmbeddingServiceExportFileSchema(**file_data)
        
        # Import
        import_service = EmbeddingServiceImportService(db)
        summary = import_service.import_embedding_service(
            export_data,
            app_id,
            conflict_mode,
            new_name
        )
        
        return ImportResponseSchema(
            success=True,
            message=f"Embedding Service '{summary.component_name}' imported successfully",
            summary=summary
        )
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(
                status.HTTP_409_CONFLICT, str(e)
            )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        logger.error(f"Import error: {str(e)}", exc_info=True)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Import failed",
        )


# ==================== DYNAMIC ROUTES (with {service_id} parameter) ====================


@embedding_services_router.get("/{service_id}",
                               summary="Get embedding service details",
                               tags=["Embedding Services"],
                               response_model=EmbeddingServiceDetailSchema)
async def get_embedding_service(
    app_id: int,
    service_id: int,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """
    Get detailed information about a specific embedding service.
    """
    
    try:
        service_detail = EmbeddingServiceService.get_embedding_service_detail(db, app_id, service_id)
        
        if service_detail is None and service_id != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=EMBEDDING_SERVICE_NOT_FOUND_MSG
            )
        
        return service_detail
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving embedding service: {str(e)}"
        )


@embedding_services_router.post("/{service_id}",
                                summary="Create or update embedding service",
                                tags=["Embedding Services"],
                                response_model=EmbeddingServiceDetailSchema)
async def create_or_update_embedding_service(
    app_id: int,
    service_id: int,
    service_data: CreateUpdateEmbeddingServiceSchema,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """
    Create a new embedding service or update an existing one.
    """
    
    try:
        service = EmbeddingServiceService.create_or_update_embedding_service(
            db, app_id, service_id, service_data
        )
        
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=EMBEDDING_SERVICE_NOT_FOUND_MSG
            )
        
        # Return updated service details
        return EmbeddingServiceService.get_embedding_service_detail(db, app_id, service.service_id)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating embedding service: {str(e)}"
        )


@embedding_services_router.delete("/{service_id}",
                                  summary="Delete embedding service",
                                  tags=["Embedding Services"])
async def delete_embedding_service(
    app_id: int,
    service_id: int,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """
    Delete an embedding service.
    """
    
    try:
        success = EmbeddingServiceService.delete_embedding_service(db, app_id, service_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=EMBEDDING_SERVICE_NOT_FOUND_MSG
            )
        
        return {"message": "Embedding service deleted successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting embedding service: {str(e)}"
        )


# ==================== EXPORT/IMPORT ENDPOINTS ====================


@embedding_services_router.post(
    "/{service_id}/export",
    summary="Export Embedding Service",
    tags=["Embedding Services", "Export/Import"],
    status_code=status.HTTP_200_OK
)
async def export_embedding_service(
    app_id: int,
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """Export Embedding Service configuration to JSON file."""
    try:
        export_service = EmbeddingServiceExportService(db)
        export_data = export_service.export_embedding_service(
            service_id,
            app_id,
            getattr(auth_context, 'user_id', None)
        )
        
        filename = f"{export_data.embedding_service.name.replace(' ', '_')}_embedding_service.json"
        
        return JSONResponse(
            content=export_data.model_dump(mode='json'),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ValueError as e:
        logger.warning(f"Export failed: {str(e)}")
        if "not found" in str(e):
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        logger.error(f"Export error: {str(e)}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Export failed") 