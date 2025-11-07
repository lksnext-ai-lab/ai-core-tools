from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
import json
import tempfile
import os

# Import our services
from services.agent_service import AgentService
from services.silo_service import SiloService
from services.repository_service import RepositoryService
from services.resource_service import ResourceService

# Import Pydantic models and auth
from .schemas import *
from .auth import get_api_key_auth, validate_api_key_for_app, APIKeyAuth
from db.database import get_db

# Import schemas from backend schemas
from schemas.silo_schemas import (
    SiloListItemSchema, SiloDetailSchema, CreateUpdateSiloSchema
)

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

# Constants
SILO_NOT_FOUND_MSG = "Silo not found"

silos_router = APIRouter()

# ==================== SILO CRUD ENDPOINTS ====================

@silos_router.post("/",
                   summary="Create new silo",
                   tags=["Silos"],
                   response_model=SiloDetailSchema)
async def create_silo(
    app_id: int,
    silo_data: CreateUpdateSiloSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """
    Create a new silo/collection.
    """
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        # Create silo using the service (silo_id = 0 for new silo)
        silo = SiloService.create_or_update_silo_router(
            app_id=app_id,
            silo_id=0,  # 0 indicates new silo
            silo_data=silo_data,
            db=db
        )
        
        # Return the created silo details
        return SiloService.get_silo_detail(app_id, silo.silo_id, db)
        
    except Exception as e:
        logger.error(f"Error creating silo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating silo: {str(e)}")


@silos_router.get("/",
                  summary="List all silos",
                  tags=["Silos"],
                  response_model=List[SiloListItemSchema])
async def list_silos(
    app_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page"),
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """
    List all silos with filtering/pagination.
    """
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        # Get all silos for the app
        silos = SiloService.get_silos_list(app_id, db)
        
        # Apply pagination
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        paginated_silos = silos[start_index:end_index]
        
        return paginated_silos
        
    except Exception as e:
        logger.error(f"Error listing silos: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing silos: {str(e)}")


@silos_router.get("/{silo_id}",
                  summary="Get silo details",
                  tags=["Silos"],
                  response_model=SiloDetailSchema)
async def get_silo(
    app_id: int,
    silo_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """
    Get silo details.
    """
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        # Get silo details
        silo_detail = SiloService.get_silo_detail(app_id, silo_id, db)
        
        if silo_detail is None:
            raise HTTPException(status_code=404, detail=SILO_NOT_FOUND_MSG)
        
        return silo_detail
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting silo details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting silo details: {str(e)}")


@silos_router.put("/{silo_id}",
                  summary="Update silo properties",
                  tags=["Silos"],
                  response_model=SiloDetailSchema)
async def update_silo(
    app_id: int,
    silo_id: int,
    silo_data: CreateUpdateSiloSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """
    Update silo properties.
    """
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        # Check if silo exists
        existing_silo = SiloService.get_silo(silo_id, db)
        if not existing_silo:
            raise HTTPException(status_code=404, detail=SILO_NOT_FOUND_MSG)
        
        # Check if silo belongs to the app
        if existing_silo.app_id != app_id:
            raise HTTPException(status_code=403, detail="Silo does not belong to this app")
        
        # Update silo using the service
        silo = SiloService.create_or_update_silo_router(
            app_id=app_id,
            silo_id=silo_id,
            silo_data=silo_data,
            db=db
        )
        
        # Return the updated silo details
        return SiloService.get_silo_detail(app_id, silo.silo_id, db)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating silo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating silo: {str(e)}")


@silos_router.delete("/{silo_id}",
                     summary="Delete silo and all contents",
                     tags=["Silos"],
                     response_model=MessageResponseSchema)
async def delete_silo(
    app_id: int,
    silo_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """
    Delete silo and all contents.
    """
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        # Check if silo exists
        existing_silo = SiloService.get_silo(silo_id, db)
        if not existing_silo:
            raise HTTPException(status_code=404, detail=SILO_NOT_FOUND_MSG)
        
        # Check if silo belongs to the app
        if existing_silo.app_id != app_id:
            raise HTTPException(status_code=403, detail="Silo does not belong to this app")
        
        # Delete silo using the service
        success = SiloService.delete_silo_router(silo_id, db)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete silo")
        
        return MessageResponseSchema(message="Silo and all contents deleted successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting silo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting silo: {str(e)}")


# ==================== SILO DOCUMENT OPERATIONS ====================

@silos_router.get("/silos/{silo_id}/docs",
                  summary="Count docs in silo",
                  tags=["Silos"],
                  response_model=CountResponseSchema)
async def count_docs_in_silo(
    app_id: int,
    silo_id: int,
    api_key: str = Depends(get_api_key_auth)
):
    """Count documents in a silo."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    # TODO: Implement silo document counting
    return CountResponseSchema(count=0)

@silos_router.post("/silos/{silo_id}/docs/index",
                   summary="Index content",
                   tags=["Silos"],
                   response_model=MessageResponseSchema)
async def index_single_document(
    app_id: int,
    silo_id: int,
    request: SingleDocumentIndexSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """Index a single document in a silo."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        SiloService.index_single_content(
            silo_id=silo_id,
            content=request.content,
            metadata=request.metadata or {},
            db=db
        )
        return MessageResponseSchema(message="Document indexed successfully")
    except Exception as e:
        logger.error(f"Error indexing document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error indexing document: {str(e)}")

@silos_router.post("/silos/{silo_id}/docs/multiple-index",
                   summary="Index multiple documents",
                   tags=["Silos"],
                   response_model=MessageResponseSchema)
async def index_multiple_documents(
    app_id: int,
    silo_id: int,
    request: MultipleDocumentIndexSchema,
    api_key: str = Depends(get_api_key_auth)
):
    """Index multiple documents in a silo."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    # TODO: Implement multiple document indexing
    return MessageResponseSchema(message="Documents indexed successfully")

@silos_router.delete("/silos/{silo_id}/docs/delete",
                     summary="Delete docs in collection",
                     tags=["Silos"],
                     response_model=MessageResponseSchema)
async def delete_docs_in_collection(
    app_id: int,
    silo_id: int,
    request: DeleteDocsRequestSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """Delete documents in a silo collection."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        SiloService.delete_docs_in_collection(silo_id, request.ids, db)
        return MessageResponseSchema(message=f"Successfully deleted {len(request.ids)} document(s)")
    except Exception as e:
        logger.error(f"Error deleting documents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting documents: {str(e)}")

@silos_router.delete("/silos/{silo_id}/docs/delete/all",
                     summary="Delete all docs in collection",
                     tags=["Silos"],
                     response_model=MessageResponseSchema)
async def delete_all_docs_in_collection(
    app_id: int,
    silo_id: int,
    api_key: str = Depends(get_api_key_auth)
):
    """Delete all documents in a silo collection."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    # TODO: Implement all document deletion
    return MessageResponseSchema(message="All documents deleted successfully")

@silos_router.post("/silos/{silo_id}/docs/find",
                   summary="Find docs in collection",
                   tags=["Silos"],
                   response_model=DocsResponseSchema)
async def find_docs_in_collection(
    app_id: int,
    silo_id: int,
    request: SiloSearchSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """Find documents in a silo collection."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        query = request.query if request.query else " "
        docs = SiloService.find_docs_in_collection(
            silo_id=silo_id,
            query=query,
            filter_metadata=request.filter_metadata,
            db=db
        )
        
        doc_schemas = []
        for doc in docs:
            # Try to get ID from document object first, then from metadata
            doc_id = getattr(doc, 'id', None) or doc.metadata.get("_id") or doc.metadata.get("id") or ""
            doc_schemas.append({
                "page_content": doc.page_content,
                "metadata": {**doc.metadata, "id": str(doc_id) if doc_id else ""}
            })
        
        return DocsResponseSchema(docs=doc_schemas)
    except Exception as e:
        logger.error(f"Error finding documents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error finding documents: {str(e)}")

@silos_router.post("/silos/{silo_id}/docs/index-file",
                   summary="Index file content",
                   tags=["Silos"],
                   response_model=FileIndexResponseSchema)
async def index_file_document(
    app_id: int,
    silo_id: int,
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """Index file content in a silo."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    import tempfile
    import os
    from services.silo_service import SiloService
    from repositories.silo_repository import SiloRepository
    from db.database import db as db_obj
    from tools.pgVectorTools import PGVectorTools
    from services.silo_service import COLLECTION_PREFIX
    
    temp_file_path = None
    try:
        # Get silo to verify it exists and get embedding service
        silo = SiloRepository.get_by_id(silo_id, db)
        if not silo:
            raise HTTPException(status_code=404, detail=f"Silo {silo_id} not found")
        
        if not silo.embedding_service:
            raise HTTPException(status_code=400, detail=f"Silo {silo_id} has no embedding service configured")
        
        # Parse metadata if provided
        metadata_dict = {}
        if metadata:
            try:
                import json
                metadata_dict = json.loads(metadata)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON metadata: {metadata}, using empty dict")
        
        # Save uploaded file to temporary location
        file_extension = os.path.splitext(file.filename or "")[1].lower()
        if not file_extension:
            # Try to determine from content type
            if file.content_type:
                content_type_map = {
                    'application/pdf': '.pdf',
                    'application/msword': '.doc',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
                    'text/plain': '.txt'
                }
                file_extension = content_type_map.get(file.content_type, '.txt')
            else:
                file_extension = '.txt'
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            temp_file_path = temp_file.name
            # Read file content
            content = await file.read()
            temp_file.write(content)
        
        # Extract documents from file
        docs = SiloService.extract_documents_from_file(temp_file_path, file_extension, metadata_dict)
        
        # Index documents using PGVector
        collection_name = COLLECTION_PREFIX + str(silo_id)
        pg_vector_tools = PGVectorTools(db_obj)
        pg_vector_tools.index_documents(collection_name, docs, silo.embedding_service)
        
        logger.info(f"Successfully indexed file {file.filename} in silo {silo_id}, {len(docs)} documents")
        
        return FileIndexResponseSchema(
            message="File indexed successfully",
            num_documents=len(docs)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error indexing file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error indexing file: {str(e)}")
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_file_path}: {str(e)}") 