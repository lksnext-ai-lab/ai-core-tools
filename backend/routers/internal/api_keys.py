from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

# Import services
from services.api_key_service import APIKeyService

# Import schemas and auth
from schemas.api_key_schemas import *
from .auth_utils import get_current_user_oauth

# Import database dependency
from db.database import get_db

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

api_keys_router = APIRouter()

# Create service instance
api_key_service = APIKeyService()

# ==================== API KEY MANAGEMENT ====================

@api_keys_router.get("/", 
                    summary="List API keys",
                    tags=["API Keys"],
                    response_model=List[APIKeyListItemSchema])
async def list_api_keys(
    app_id: int, 
    current_user: dict = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    List all API keys for a specific app.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        return api_key_service.get_api_keys_list(db, app_id)
    except Exception as e:
        logger.error(f"Error retrieving API keys for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving API keys: {str(e)}"
        )


@api_keys_router.get("/{key_id}",
                    summary="Get API key details",
                    tags=["API Keys"],
                    response_model=APIKeyDetailSchema)
async def get_api_key(
    app_id: int, 
    key_id: int, 
    current_user: dict = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific API key.
    Note: The actual key value is only shown once upon creation.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        api_key_detail = api_key_service.get_api_key_detail(db, app_id, key_id)
        
        if api_key_detail is None and key_id != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        return api_key_detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving API key {key_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving API key: {str(e)}"
        )


@api_keys_router.post("/{key_id}",
                     summary="Create or update API key",
                     tags=["API Keys"],
                     response_model=APIKeyCreateResponseSchema)
async def create_or_update_api_key(
    app_id: int,
    key_id: int,
    api_key_data: CreateUpdateAPIKeySchema,
    current_user: dict = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Create a new API key or update an existing one.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        if key_id == 0:
            # Create new API key
            return api_key_service.create_api_key(
                db, app_id, user_id, api_key_data.name, api_key_data.is_active
            )
        else:
            # Update existing API key
            updated_key = api_key_service.update_api_key(
                db, app_id, key_id, api_key_data.name, api_key_data.is_active
            )
            
            if updated_key is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="API key not found"
                )
            
            return updated_key
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating/updating API key for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating API key: {str(e)}"
        )


@api_keys_router.delete("/{key_id}",
                       summary="Delete API key",
                       tags=["API Keys"])
async def delete_api_key(
    app_id: int, 
    key_id: int, 
    current_user: dict = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Delete an API key.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        deleted = api_key_service.delete_api_key(db, app_id, key_id)
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        return {"message": "API key deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting API key {key_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting API key: {str(e)}"
        )


@api_keys_router.post("/{key_id}/toggle",
                     summary="Toggle API key active status",
                     tags=["API Keys"])
async def toggle_api_key(
    app_id: int, 
    key_id: int, 
    current_user: dict = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Toggle the active status of an API key.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        message = api_key_service.toggle_api_key(db, app_id, key_id)
        
        if message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        return {"message": message}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling API key {key_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error toggling API key: {str(e)}"
        ) 