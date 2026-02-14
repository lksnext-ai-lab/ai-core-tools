from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, UploadFile, File, Query
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
import json

from services.silo_service import SiloService
from services.silo_export_service import SiloExportService
from services.silo_import_service import SiloImportService

from schemas.silo_schemas import (
    SiloListItemSchema, SiloDetailSchema, CreateUpdateSiloSchema, SiloSearchSchema
)
from schemas.import_schemas import ConflictMode, ImportResponseSchema
from schemas.export_schemas import SiloExportFileSchema
from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole

from db.database import get_db

from utils.logger import get_logger


SILO_NOT_FOUND_MSG = "Silo not found"
logger = get_logger(__name__)

silos_router = APIRouter()

# ==================== SILO MANAGEMENT ====================

@silos_router.post(
    "/import",
    summary="Import Silo",
    tags=["Silos", "Export/Import"],
    response_model=ImportResponseSchema,
    status_code=status.HTTP_201_CREATED
)
async def import_silo(
    app_id: int,
    file: UploadFile = File(...),
    conflict_mode: ConflictMode = Query(ConflictMode.FAIL),
    new_name: Optional[str] = Query(None),
    selected_embedding_service_id: Optional[int] = Query(None),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """Import Silo from JSON file.
    
    Note: If embedding service is not bundled in the export file,
    you must provide selected_embedding_service_id.
    """
    try:
        # Parse file
        content = await file.read()
        file_data = json.loads(content)
        export_data = SiloExportFileSchema(**file_data)
        
        # Validate import
        import_service = SiloImportService(db)
        validation = import_service.validate_import(export_data, app_id)
        
        # Check if embedding service selection is required but not provided
        if validation.requires_embedding_service_selection:
            if selected_embedding_service_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Embedding service selection required. "
                        "This silo requires an embedding service but none is bundled. "
                        "Please provide selected_embedding_service_id parameter."
                    )
                )
        
        # Import
        summary = import_service.import_silo(
            export_data,
            app_id,
            conflict_mode,
            new_name,
            selected_embedding_service_id
        )
        
        return ImportResponseSchema(
            success=True,
            message=f"Silo '{summary.component_name}' imported successfully",
            summary=summary
        )
    except HTTPException:
        raise
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(
                status.HTTP_409_CONFLICT, str(e)
            )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        logger.error(f"Import error: {str(e)}", exc_info=True)


@silos_router.get("/", 
                  summary="List silos",
                  tags=["Silos"],
                  response_model=List[SiloListItemSchema])
async def list_silos(
    app_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    List all silos for a specific app.
    """
    
    # TODO: Add app access validation
    
    try:
        result = SiloService.get_silos_list(app_id, db)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving silos: {str(e)}"
        )


@silos_router.get("/{silo_id}",
                  summary="Get silo details",
                  tags=["Silos"],
                  response_model=SiloDetailSchema)
async def get_silo(
    app_id: int, 
    silo_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific silo including form data for editing.
    """    
    # TODO: Add app access validation
    
    try:
        result = SiloService.get_silo_detail(app_id, silo_id, db)
        if result is None and silo_id != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SILO_NOT_FOUND_MSG
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving silo: {str(e)}"
        )


@silos_router.post("/{silo_id}",
                   summary="Create or update silo",
                   tags=["Silos"],
                   response_model=SiloDetailSchema)
async def create_or_update_silo(
    app_id: int,
    silo_id: int,
    silo_data: CreateUpdateSiloSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("editor")),
    db: Session = Depends(get_db)
):
    """
    Create a new silo or update an existing one.
    """    
    # TODO: Add app access validation
    
    try:
        # Create or update using the service
        silo = SiloService.create_or_update_silo_router(app_id, silo_id, silo_data, db)
        
        # Return updated silo (reuse the GET logic)
        logger.info(f"Silo created/updated successfully: {silo.silo_id}, now getting details")
        return await get_silo(app_id, silo.silo_id, auth_context, role, db)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating/updating silo: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating silo: {str(e)}"
        )


@silos_router.delete("/{silo_id}",
                     summary="Delete silo",
                     tags=["Silos"])
async def delete_silo(
    app_id: int, 
    silo_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("editor")),
    db: Session = Depends(get_db)
):
    """
    Delete a silo and all its documents.
    """    
    # TODO: Add app access validation
    
    try:
        success = SiloService.delete_silo_router(silo_id, db)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SILO_NOT_FOUND_MSG
            )
        
        return {"message": "Silo deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting silo: {str(e)}"
        )


@silos_router.post(
    "/{silo_id}/export",
    summary="Export Silo",
    tags=["Silos", "Export/Import"],
    status_code=status.HTTP_200_OK
)
async def export_silo(
    app_id: int,
    silo_id: int,
    include_dependencies: bool = Query(True, description="Bundle dependencies (embedding service, output parser)"),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """Export Silo configuration to JSON file.
    
    Note: Exports silo STRUCTURE only (no vector embeddings).
    Vector data must be regenerated after import by uploading documents.
    """
    try:
        export_service = SiloExportService(db)
        export_data = export_service.export_silo(
            silo_id,
            app_id,
            getattr(auth_context, 'user_id', None),
            include_dependencies
        )
        
        filename = f"{export_data.silo.name.replace(' ', '_')}_silo.json"
        
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


# ==================== SILO PLAYGROUND ====================

@silos_router.get("/{silo_id}/playground",
                  summary="Get silo playground",
                  tags=["Silos", "Playground"])
async def silo_playground(
    app_id: int, 
    silo_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Get silo playground interface for testing document search.
    """
    
    # TODO: Add app access validation
    
    try:
        result = SiloService.get_silo_playground_info(silo_id, db)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SILO_NOT_FOUND_MSG
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error accessing silo playground: {str(e)}"
        )


@silos_router.post("/{silo_id}/search",
                   summary="Search documents in silo",
                   tags=["Silos", "Playground"])
async def search_silo_documents(
    app_id: int,
    silo_id: int,
    search_query: SiloSearchSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Search for documents in a silo using semantic search with optional metadata filtering.
    """
    logger.info(f"Search request received - app_id: {app_id}, silo_id: {silo_id}, user_id: {auth_context.identity.id}")
    logger.info(f"Search query: {search_query.query}, limit: {search_query.limit}, filter_metadata: {search_query.filter_metadata}")
        
    # TODO: Add app access validation
    
    try:
        logger.info(f"Getting silo {silo_id} for validation")
        
        result = SiloService.search_silo_documents_router(
            silo_id, 
            search_query.query, 
            search_query.filter_metadata,
            db
        )
        
        if result is None:
            logger.error(f"Silo {silo_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SILO_NOT_FOUND_MSG
            )
        
        logger.info(f"Search completed, found {result['total_results']} results")
        logger.info(f"Returning {result['total_results']} results to frontend")
        return result
        
    except HTTPException:
        logger.error("HTTPException in search_silo_documents, re-raising")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in search_silo_documents: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching silo: {str(e)}"
        )


@silos_router.delete("/{silo_id}/documents",
                     summary="Delete documents from silo by IDs",
                     tags=["Silos"])
async def delete_silo_documents(
    app_id: int,
    silo_id: int,
    document_ids: List[str] = Body(..., embed=True),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Delete documents from a silo by their IDs.
    Example request body: {"document_ids": ["uuid-1", "uuid-2"]}
    """    
    # TODO: Add app access validation
    
    try:
        # Validate silo exists and belongs to app
        silo = SiloService.get_silo(silo_id, db)
        if not silo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SILO_NOT_FOUND_MSG
            )
        
        if silo.app_id != app_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Silo does not belong to this app"
            )
        
        # Delete documents using existing service method
        SiloService.delete_docs_in_collection(silo_id, document_ids, db)
        
        return {
            "message": f"Successfully deleted {len(document_ids)} document(s)",
            "deleted_count": len(document_ids)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting silo documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting documents: {str(e)}"
        ) 