from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from typing import List, Dict, Any
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

from services.silo_service import SiloService

from schemas.silo_schemas import (
    SiloListItemSchema, SiloDetailSchema, CreateUpdateSiloSchema, SiloSearchSchema
)
from .auth_utils import get_current_user_oauth

from db.database import get_db

from utils.logger import get_logger


SILO_NOT_FOUND_MSG = "Silo not found"
logger = get_logger(__name__)

silos_router = APIRouter()

# ==================== SILO MANAGEMENT ====================

@silos_router.get("/", 
                  summary="List silos",
                  tags=["Silos"],
                  response_model=List[SiloListItemSchema])
async def list_silos(
    app_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
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
        return await get_silo(app_id, silo.silo_id, auth_context, db)
        
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