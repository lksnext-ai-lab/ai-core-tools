from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import JSONResponse
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from typing import List, Optional
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
    db: Session = Depends(get_db),
    role: AppRole = Depends(require_min_role("viewer")),
    auth_context: AuthContext = Depends(get_current_user_oauth)
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
    "/import",
    summary="Import Embedding Service",
    tags=["Embedding Services", "Export/Import"],
    response_model=ImportResponseSchema,
    status_code=status.HTTP_201_CREATED
)
async def import_embedding_service(
    app_id: int,
    file: UploadFile = File(...),
    conflict_mode: ConflictMode = Query(ConflictMode.FAIL),
    new_name: Optional[str] = Query(None),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        logger.error(f"Import error: {str(e)}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Import failed")


# ==================== DYNAMIC ROUTES (with {service_id} parameter) ====================


@embedding_services_router.get("/{service_id}",
                               summary="Get embedding service details",
                               tags=["Embedding Services"],
                               response_model=EmbeddingServiceDetailSchema)
async def get_embedding_service(
    app_id: int, 
    service_id: int, 
    db: Session = Depends(get_db),
    role: AppRole = Depends(require_min_role("viewer")),
    auth_context: AuthContext = Depends(get_current_user_oauth)
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
    db: Session = Depends(get_db),
    role: AppRole = Depends(require_min_role("administrator")),
    auth_context: AuthContext = Depends(get_current_user_oauth)
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
    db: Session = Depends(get_db),
    role: AppRole = Depends(require_min_role("administrator")),
    auth_context: AuthContext = Depends(get_current_user_oauth)
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
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
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