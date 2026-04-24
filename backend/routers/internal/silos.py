from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, UploadFile, File, Query
from fastapi.responses import JSONResponse
from typing import List, Annotated, Optional
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
import json

from services.silo_service import SiloService
from services.silo_export_service import SiloExportService
from services.silo_import_service import SiloImportService
from models.silo import Silo

from schemas.silo_schemas import (
    SiloListItemSchema, SiloDetailSchema, CreateUpdateSiloSchema,
    CreateSiloSchema, UpdateSiloSchema, SiloSearchSchema
)
from schemas.import_schemas import ConflictMode, ImportResponseSchema
from schemas.export_schemas import SiloExportFileSchema
from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole
from utils.error_handlers import ValidationError
from utils.vector_db_immutability import assert_vector_db_type_immutable, assert_embedding_service_immutable

from db.database import get_db

from utils.logger import get_logger


SILO_NOT_FOUND_MSG = "Silo not found"
logger = get_logger(__name__)

silos_router = APIRouter()


def _validate_silo_app_ownership(silo_id: int, app_id: int, db: Session) -> Silo:
    """
    Validate that a silo exists and belongs to the specified app.
    
    Returns the Silo object if validation passes.
    Raises HTTPException(404) if silo not found.
    Raises HTTPException(403) if silo belongs to a different app.
    """
    silo = SiloService.get_silo(silo_id, db)
    if not silo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=SILO_NOT_FOUND_MSG
        )
    if silo.app_id != app_id:
        logger.warning(
            f"Access violation: silo {silo_id} (app {silo.app_id}) accessed from app {app_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Silo does not belong to this app"
        )
    return silo

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
    file: Annotated[UploadFile, File(...)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    conflict_mode: Annotated[ConflictMode, Query()] = ConflictMode.FAIL,
    new_name: Annotated[Optional[str], Query()] = None,
    selected_embedding_service_id: Annotated[Optional[int], Query()] = None,
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
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Import failed"
        )


@silos_router.get("/", 
                  summary="List silos",
                  tags=["Silos"],
                  response_model=List[SiloListItemSchema])
async def list_silos(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """
    List all silos for a specific app.
    """
    
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
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """
    Get detailed information about a specific silo including form data for editing.
    """
    # Skip validation for silo_id == 0 (new silo creation)
    if silo_id != 0:
        _validate_silo_app_ownership(silo_id, app_id, db)

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


@silos_router.post("/",
                   summary="Create silo",
                   tags=["Silos"],
                   response_model=SiloDetailSchema,
                   status_code=status.HTTP_201_CREATED)
async def create_silo(
    app_id: int,
    silo_data: CreateSiloSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """
    Create a new silo.
    """
    try:
        silo = SiloService.create_or_update_silo_router(app_id, 0, silo_data, db)
        logger.info(f"Silo created successfully: {silo.silo_id}")
        return await get_silo(app_id, silo.silo_id, auth_context, db, role)

    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating silo: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating silo: {str(e)}"
        )


@silos_router.put("/{silo_id}",
                  summary="Update silo",
                  tags=["Silos"],
                  response_model=SiloDetailSchema)
async def update_silo(
    request: Request,
    app_id: int,
    silo_id: int,
    silo_data: UpdateSiloSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """
    Update an existing silo. Note: vector_db_type and embedding_service_id cannot be changed after creation.
    """
    _validate_silo_app_ownership(silo_id, app_id, db)

    try:
        raw_body = await request.json()
        existing_silo = SiloService.get_silo(silo_id, db)
        if existing_silo:
            assert_vector_db_type_immutable(existing_silo.vector_db_type, raw_body.get('vector_db_type'), "silo")
            assert_embedding_service_immutable(existing_silo.embedding_service_id, raw_body.get('embedding_service_id'), "silo")

        silo = SiloService.create_or_update_silo_router(app_id, silo_id, silo_data, db)
        logger.info(f"Silo updated successfully: {silo.silo_id}")
        return await get_silo(app_id, silo.silo_id, auth_context, db, role)

    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating silo: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating silo: {str(e)}"
        )


@silos_router.delete("/{silo_id}",
                     summary="Delete silo",
                     tags=["Silos"])
async def delete_silo(
    app_id: int,
    silo_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """
    Delete a silo and all its documents.
    """    
    _validate_silo_app_ownership(silo_id, app_id, db)
    
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
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    include_dependencies: Annotated[bool, Query(description="Bundle dependencies (embedding service, output parser)")] = True,
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


@silos_router.post("/{silo_id}/search",
                   summary="Search documents in silo",
                   tags=["Silos", "Playground"])
async def search_silo_documents(
    app_id: int,
    silo_id: int,
    search_query: SiloSearchSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """
    Search for documents in a silo using semantic search with optional metadata filtering.
    """
    logger.info(f"Search request received - app_id: {app_id}, silo_id: {silo_id}, user_id: {auth_context.identity.id}")
    logger.info(f"Search query: {search_query.query}, limit: {search_query.limit}, filter_metadata: {search_query.filter_metadata}")
        
    _validate_silo_app_ownership(silo_id, app_id, db)
    
    try:
        logger.info(f"Getting silo {silo_id} for validation")
        
        result = SiloService.search_silo_documents_router(
            silo_id,
            search_query.query,
            search_query.filter_metadata,
            search_query.limit,
            search_query.search_type,
            search_query.score_threshold,
            search_query.fetch_k,
            search_query.lambda_mult,
            db,
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


@silos_router.get(
    "/{silo_id}/documents/neighbors",
    summary="Get neighboring chunks from same source document",
    tags=["Silos"],
)
async def get_neighboring_chunks(
    app_id: int,
    silo_id: int,
    source_type: Annotated[str, Query(..., description="'media' or 'resource'")],
    source_id: Annotated[str, Query(..., description="The media_id or resource_id value")],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """
    Return all chunks belonging to the same source document (media or resource),
    ordered by their position (chunk_index for media, page for resources).
    """
    _validate_silo_app_ownership(silo_id, app_id, db)
    try:
        chunks = SiloService.get_neighboring_chunks(silo_id, source_type, source_id, db)
        return {"source_type": source_type, "source_id": source_id, "chunks": chunks, "total": len(chunks)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@silos_router.get(
    "/{silo_id}/metadata/{field}/values",
    summary="Get distinct values for a silo metadata field",
    tags=["Silos"],
)
async def get_metadata_field_values(
    app_id: int,
    silo_id: int,
    field: str,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    prefix: Annotated[Optional[str], Query(description="Filter by value prefix (case-insensitive)")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """
    Distinct values for a metadata field — powers autocomplete in the filter UI.
    """
    _validate_silo_app_ownership(silo_id, app_id, db)
    try:
        values = SiloService.get_metadata_field_values(silo_id, field, prefix=prefix, limit=limit, db=db)
        return {"field": field, "values": values, "total": len(values)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@silos_router.post(
    "/{silo_id}/documents/count",
    summary="Count documents matching a metadata filter (dry-run for delete-by-filter)",
    tags=["Silos"],
)
async def count_silo_documents(
    app_id: int,
    silo_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
    filter_metadata: Annotated[Optional[dict], Body(embed=True)] = None,
):
    """
    Returns the number of documents matching the given filter.
    Pass an empty body or omit filter_metadata to count all documents.
    Used as dry-run before delete-by-filter.
    """
    _validate_silo_app_ownership(silo_id, app_id, db)
    try:
        count = SiloService.count_docs_with_filter(silo_id, filter_metadata, db)
        return {"silo_id": silo_id, "count": count, "filter_applied": filter_metadata is not None}
    except Exception as e:
        logger.error(f"Error counting silo documents: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@silos_router.post(
    "/{silo_id}/resources/{resource_id}/reindex",
    summary="Reindex a single repository resource into this silo",
    tags=["Silos"],
)
async def reindex_silo_resource(
    app_id: int,
    silo_id: int,
    resource_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """
    Re-extracts and re-indexes a single Resource document into the silo.
    The resource must belong to a repository whose silo_id matches this silo.
    """
    _validate_silo_app_ownership(silo_id, app_id, db)
    from models.resource import Resource
    resource = db.query(Resource).filter(Resource.resource_id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if resource.repository.silo_id != silo_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resource does not belong to this silo",
        )
    try:
        SiloService.index_resource(resource)
        return {"message": f"Resource {resource_id} reindexed successfully", "resource_id": resource_id}
    except Exception as e:
        logger.error(f"Error reindexing resource {resource_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@silos_router.delete("/{silo_id}/documents",
                     summary="Delete documents from silo by IDs",
                     tags=["Silos"])
async def delete_silo_documents(
    app_id: int,
    silo_id: int,
    document_ids: Annotated[List[str], Body(..., embed=True)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """
    Delete documents from a silo by their IDs.
    Example request body: {"document_ids": ["uuid-1", "uuid-2"]}
    """    
    try:
        # Validate silo exists and belongs to app
        _validate_silo_app_ownership(silo_id, app_id, db)
        
        # Delete documents using existing service method
        SiloService.delete_docs_in_collection(silo_id, document_ids, db)
        
        return {
            "message": f"Successfully deleted {len(document_ids)} document(s)",
            "deleted_count": len(document_ids)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting silo documents: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting documents: {str(e)}"
        ) 
