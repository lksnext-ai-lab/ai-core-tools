from fastapi import APIRouter, Depends, HTTPException, status
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from typing import List

# Import schemas and auth
from schemas.embedding_service_schemas import (
    EmbeddingServiceListItemSchema,
    EmbeddingServiceDetailSchema,
    CreateUpdateEmbeddingServiceSchema
)
from .auth_utils import get_current_user_oauth

# Import database dependency
from db.database import get_db

# Import service
from services.embedding_service_service import EmbeddingServiceService

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
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    List all embedding services for a specific app.
    """
    user_id = int(auth_context.identity.id)
    
    # TODO: Add app access validation
    
    try:
        return EmbeddingServiceService.get_embedding_services_list(db, app_id)
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving embedding services: {str(e)}"
        )


@embedding_services_router.get("/{service_id}",
                               summary="Get embedding service details",
                               tags=["Embedding Services"],
                               response_model=EmbeddingServiceDetailSchema)
async def get_embedding_service(
    app_id: int, 
    service_id: int, 
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Get detailed information about a specific embedding service.
    """
    user_id = int(auth_context.identity.id)
    
    # TODO: Add app access validation
    
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
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Create a new embedding service or update an existing one.
    """    
    # TODO: Add app access validation
    
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
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Delete an embedding service.
    """
    
    # TODO: Add app access validation
    
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