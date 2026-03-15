from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from typing import Optional, Annotated
from sqlalchemy.orm import Session
import json
import tempfile
import os

from services.silo_service import SiloService

from .schemas import (
    MessageResponseSchema,
    CountResponseSchema,
    SingleDocumentIndexSchema,
    MultipleDocumentIndexSchema,
    DeleteDocsRequestSchema,
    DeleteByMetadataRequestSchema,
    DocsResponseSchema,
    FileIndexResponseSchema,
    PublicSiloSchema,
    PublicSiloResponseSchema,
    PublicSilosResponseSchema,
    PublicSiloSearchResultSchema,
    PublicSiloSearchResponseSchema,
)
from .auth import get_api_key_auth, validate_api_key_for_app, validate_silo_ownership
from db.database import get_db

from schemas.silo_schemas import CreateUpdateSiloSchema, SiloSearchSchema

from utils.logger import get_logger

logger = get_logger(__name__)

SILO_NOT_FOUND_MSG = "Silo not found"

silos_router = APIRouter()


# ==================== SILO CRUD ENDPOINTS ====================


@silos_router.post(
    "/",
    summary="Create new silo",
    tags=["Silos"],
    response_model=PublicSiloResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_silo(
    app_id: int,
    silo_data: CreateUpdateSiloSchema,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Create a new silo/collection."""
    validate_api_key_for_app(app_id, api_key, db)

    try:
        silo = SiloService.create_or_update_silo_router(
            app_id=app_id,
            silo_id=0,
            silo_data=silo_data,
            db=db,
        )

        silo_detail = SiloService.get_silo_detail(app_id, silo.silo_id, db)
        public_silo = PublicSiloSchema.model_validate(silo_detail)

        logger.info(f"Created silo {silo.silo_id} for app {app_id}")
        return PublicSiloResponseSchema(silo=public_silo)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating silo for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create silo",
        )


@silos_router.get(
    "/",
    summary="List all silos",
    tags=["Silos"],
    response_model=PublicSilosResponseSchema,
)
async def list_silos(
    app_id: int,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """List all silos for the app."""
    validate_api_key_for_app(app_id, api_key, db)

    try:
        silos = SiloService.get_silos_list(app_id, db)
        public_silos = [PublicSiloSchema.model_validate(s) for s in silos]
        return PublicSilosResponseSchema(silos=public_silos)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing silos for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to list silos",
        )


@silos_router.get(
    "/{silo_id}",
    summary="Get silo details",
    tags=["Silos"],
    response_model=PublicSiloResponseSchema,
)
async def get_silo(
    app_id: int,
    silo_id: int,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Get silo details."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_silo_ownership(db, silo_id, app_id)

    try:
        silo_detail = SiloService.get_silo_detail(app_id, silo_id, db)
        if silo_detail is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SILO_NOT_FOUND_MSG,
            )
        public_silo = PublicSiloSchema.model_validate(silo_detail)
        return PublicSiloResponseSchema(silo=public_silo)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting silo {silo_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to get silo",
        )


@silos_router.put(
    "/{silo_id}",
    summary="Update silo properties",
    tags=["Silos"],
    response_model=PublicSiloResponseSchema,
)
async def update_silo(
    app_id: int,
    silo_id: int,
    silo_data: CreateUpdateSiloSchema,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Update silo properties."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_silo_ownership(db, silo_id, app_id)

    try:
        silo = SiloService.create_or_update_silo_router(
            app_id=app_id,
            silo_id=silo_id,
            silo_data=silo_data,
            db=db,
        )

        silo_detail = SiloService.get_silo_detail(app_id, silo.silo_id, db)
        public_silo = PublicSiloSchema.model_validate(silo_detail)

        logger.info(f"Updated silo {silo_id} for app {app_id}")
        return PublicSiloResponseSchema(silo=public_silo)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating silo {silo_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update silo",
        )


@silos_router.delete(
    "/{silo_id}",
    summary="Delete silo and all contents",
    tags=["Silos"],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_silo(
    app_id: int,
    silo_id: int,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Delete silo and all contents."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_silo_ownership(db, silo_id, app_id)

    try:
        success = SiloService.delete_silo_router(silo_id, db)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to delete silo",
            )

        logger.info(f"Deleted silo {silo_id} from app {app_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting silo {silo_id} from app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to delete silo",
        )


# ==================== SILO SEARCH ====================


@silos_router.post(
    "/{silo_id}/search",
    summary="Search documents in silo",
    tags=["Silos"],
    response_model=PublicSiloSearchResponseSchema,
)
async def search_silo(
    app_id: int,
    silo_id: int,
    request: SiloSearchSchema,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Search for documents in a silo using semantic search with optional metadata filtering."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_silo_ownership(db, silo_id, app_id)

    try:
        result = SiloService.search_silo_documents_router(
            silo_id, request.query, request.filter_metadata, db
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SILO_NOT_FOUND_MSG,
            )

        return PublicSiloSearchResponseSchema(
            query=result["query"],
            results=[
                PublicSiloSearchResultSchema(**r) for r in result["results"]
            ],
            total_results=result["total_results"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching silo {silo_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to search silo",
        )


# ==================== SILO DOCUMENT OPERATIONS ====================


@silos_router.get(
    "/{silo_id}/docs",
    summary="Count docs in silo",
    tags=["Silos"],
    response_model=CountResponseSchema,
)
async def count_docs_in_silo(
    app_id: int,
    silo_id: int,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Count documents in a silo."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_silo_ownership(db, silo_id, app_id)

    try:
        count = SiloService.count_docs_in_silo(silo_id, db)
        return CountResponseSchema(count=count)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error counting documents in silo {silo_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to count documents",
        )


@silos_router.post(
    "/{silo_id}/docs/index",
    summary="Index content",
    tags=["Silos"],
    response_model=MessageResponseSchema,
)
async def index_single_document(
    app_id: int,
    silo_id: int,
    request: SingleDocumentIndexSchema,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Index a single document in a silo."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_silo_ownership(db, silo_id, app_id)

    try:
        SiloService.index_single_content(
            silo_id=silo_id,
            content=request.content,
            metadata=request.metadata or {},
            db=db,
        )
        return MessageResponseSchema(message="Document indexed successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error indexing document in silo {silo_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to index document",
        )


@silos_router.post(
    "/{silo_id}/docs/multiple-index",
    summary="Index multiple documents",
    tags=["Silos"],
    response_model=MessageResponseSchema,
)
async def index_multiple_documents(
    app_id: int,
    silo_id: int,
    request: MultipleDocumentIndexSchema,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Index multiple documents in a silo."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_silo_ownership(db, silo_id, app_id)

    try:
        documents = [doc if isinstance(doc, dict) else doc.model_dump() for doc in request.documents]
        SiloService.index_multiple_content(silo_id, documents, db)
        return MessageResponseSchema(
            message=f"Successfully indexed {len(documents)} document(s)"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error indexing multiple documents in silo {silo_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to index documents",
        )


@silos_router.delete(
    "/{silo_id}/docs/delete",
    summary="Delete docs in collection",
    tags=["Silos"],
    response_model=MessageResponseSchema,
)
async def delete_docs_in_collection(
    app_id: int,
    silo_id: int,
    request: DeleteDocsRequestSchema,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Delete documents in a silo collection by IDs."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_silo_ownership(db, silo_id, app_id)

    try:
        SiloService.delete_docs_in_collection(silo_id, request.ids, db)
        return MessageResponseSchema(
            message=f"Successfully deleted {len(request.ids)} document(s)"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting documents in silo {silo_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to delete documents",
        )


@silos_router.delete(
    "/{silo_id}/docs/delete-by-metadata",
    summary="Delete docs by metadata filter",
    tags=["Silos"],
    response_model=MessageResponseSchema,
)
async def delete_docs_by_metadata(
    app_id: int,
    silo_id: int,
    request: DeleteByMetadataRequestSchema,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Delete documents by metadata filter (MongoDB-style operators)."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_silo_ownership(db, silo_id, app_id)

    try:
        if not request.filter_metadata:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="filter_metadata cannot be empty",
            )

        deleted_count = SiloService.delete_docs_by_metadata(
            silo_id=silo_id,
            filter_metadata=request.filter_metadata,
            db=db,
        )

        return MessageResponseSchema(
            message=f"Successfully deleted {deleted_count} document(s)"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting documents by metadata in silo {silo_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to delete documents",
        )


@silos_router.delete(
    "/{silo_id}/docs/delete/all",
    summary="Delete all docs in collection",
    tags=["Silos"],
    response_model=MessageResponseSchema,
)
async def delete_all_docs_in_collection(
    app_id: int,
    silo_id: int,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Delete all documents in a silo collection."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_silo_ownership(db, silo_id, app_id)

    try:
        SiloService.delete_all_docs_in_collection(silo_id, db)
        return MessageResponseSchema(message="All documents deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting all documents in silo {silo_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to delete all documents",
        )


@silos_router.post(
    "/{silo_id}/docs/find",
    summary="Find docs in collection",
    tags=["Silos"],
    response_model=DocsResponseSchema,
)
async def find_docs_in_collection(
    app_id: int,
    silo_id: int,
    request: SiloSearchSchema,
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Find documents in a silo collection."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_silo_ownership(db, silo_id, app_id)

    try:
        query = request.query if request.query else " "
        docs = SiloService.find_docs_in_collection(
            silo_id=silo_id,
            query=query,
            filter_metadata=request.filter_metadata,
            db=db,
        )

        doc_schemas = []
        for doc in docs:
            doc_id = (
                getattr(doc, "id", None)
                or doc.metadata.get("_id")
                or doc.metadata.get("id")
                or ""
            )
            doc_schemas.append(
                {
                    "page_content": doc.page_content,
                    "metadata": {
                        **doc.metadata,
                        "id": str(doc_id) if doc_id else "",
                    },
                }
            )

        return DocsResponseSchema(docs=doc_schemas)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding documents in silo {silo_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to find documents",
        )


@silos_router.post(
    "/{silo_id}/docs/index-file",
    summary="Index file content",
    tags=["Silos"],
    response_model=FileIndexResponseSchema,
)
def index_file_document(
    app_id: int,
    silo_id: int,
    file: Annotated[UploadFile, File(...)],
    api_key: Annotated[str, Depends(get_api_key_auth)],
    db: Annotated[Session, Depends(get_db)],
    metadata: Annotated[Optional[str], Form()] = None,
):
    """Index file content in a silo."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_silo_ownership(db, silo_id, app_id)

    temp_file_path = None
    try:
        metadata_dict = {}
        if metadata:
            try:
                metadata_dict = json.loads(metadata)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON metadata: Will use empty dict!")

        file_extension = os.path.splitext(file.filename or "")[1].lower()
        if not file_extension:
            if file.content_type:
                content_type_map = {
                    "application/pdf": ".pdf",
                    "application/msword": ".doc",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                    "text/plain": ".txt",
                }
                file_extension = content_type_map.get(file.content_type, ".txt")
            else:
                file_extension = ".txt"

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=file_extension
        ) as temp_file:
            temp_file_path = temp_file.name
            content = file.file.read()
            temp_file.write(content)

        docs = SiloService.extract_documents_from_file(
            temp_file_path, file_extension, metadata_dict
        )

        documents_for_indexing = [
            {"content": doc.page_content, "metadata": doc.metadata} for doc in docs
        ]

        SiloService.index_multiple_content(silo_id, documents_for_indexing, db)

        logger.info(
            f"Successfully indexed file {file.filename} in silo {silo_id}, {len(docs)} documents"
        )

        return FileIndexResponseSchema(
            message="File indexed successfully", num_documents=len(docs)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error indexing file in silo {silo_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to index file",
        )
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_file_path}: {str(e)}")

