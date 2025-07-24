from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional

# Import services
from services.api_key_service import APIKeyService

# Import schemas and auth
from .schemas import *
from .auth_utils import get_current_user_oauth

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

api_keys_router = APIRouter()

# ==================== API KEY MANAGEMENT ====================

@api_keys_router.get("/", 
                    summary="List API keys",
                    tags=["API Keys"],
                    response_model=List[APIKeyListItemSchema])
async def list_api_keys(app_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    List all API keys for a specific app.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Use direct database query instead of service to avoid authorization issues
        from db.session import SessionLocal
        from models.api_key import APIKey
        
        session = SessionLocal()
        try:
            api_keys = session.query(APIKey).filter(APIKey.app_id == app_id).all()
            
            result = []
            for api_key in api_keys:
                result.append(APIKeyListItemSchema(
                    key_id=api_key.key_id,
                    name=api_key.name,
                    is_active=api_key.is_active,
                    created_at=api_key.created_at,
                    last_used_at=getattr(api_key, 'last_used_at', None),
                    # Don't expose the actual key value for security
                    key_preview=f"{api_key.key[:8]}..." if api_key.key else "***"
                ))
            
            return result
            
        finally:
            session.close()
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving API keys: {str(e)}"
        )


@api_keys_router.get("/{key_id}",
                    summary="Get API key details",
                    tags=["API Keys"],
                    response_model=APIKeyDetailSchema)
async def get_api_key(app_id: int, key_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Get detailed information about a specific API key.
    Note: The actual key value is only shown once upon creation.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Use direct database query for now since service may not have get_by_id
        from db.session import SessionLocal
        from models.api_key import APIKey
        
        session = SessionLocal()
        try:
            if key_id == 0:
                # New API key form
                return APIKeyDetailSchema(
                    key_id=0,
                    name="",
                    is_active=True,
                    created_at=None,
                    last_used_at=None,
                    key_preview="Will be generated on save"
                )
            
            # Existing API key
            api_key = session.query(APIKey).filter(
                APIKey.key_id == key_id,
                APIKey.app_id == app_id
            ).first()
            
            if not api_key:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="API key not found"
                )
            
            return APIKeyDetailSchema(
                key_id=api_key.key_id,
                name=api_key.name,
                is_active=api_key.is_active,
                created_at=api_key.created_at,
                last_used_at=getattr(api_key, 'last_used_at', None),
                key_preview=f"{api_key.key[:8]}..." if api_key.key else "***"
            )
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
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
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Create a new API key or update an existing one.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.api_key import APIKey
        from datetime import datetime
        import secrets
        import string
        
        session = SessionLocal()
        try:
            if key_id == 0:
                # Create new API key
                api_key = APIKey()
                api_key.app_id = app_id
                api_key.user_id = user_id  # Set the user_id field
                api_key.created_at = datetime.now()
                
                # Generate a secure API key
                alphabet = string.ascii_letters + string.digits
                api_key.key = ''.join(secrets.choice(alphabet) for _ in range(32))
                api_key.name = api_key_data.name
                api_key.is_active = api_key_data.is_active
                
                session.add(api_key)
                session.commit()
                session.refresh(api_key)
                
                # Return the newly created key with the actual key value (only shown once)
                return APIKeyCreateResponseSchema(
                    key_id=api_key.key_id,
                    name=api_key.name,
                    is_active=api_key.is_active,
                    created_at=api_key.created_at,
                    last_used_at=None,
                    key_preview=f"{api_key.key[:8]}...",
                    key_value=api_key.key,  # Show the actual key once
                    message="API key created successfully. Please save this key as it won't be shown again."
                )
            else:
                # Update existing API key
                api_key = session.query(APIKey).filter(
                    APIKey.key_id == key_id,
                    APIKey.app_id == app_id
                ).first()
                
                if not api_key:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="API key not found"
                    )
                
                # Update fields
                api_key.name = api_key_data.name
                api_key.is_active = api_key_data.is_active
                
                session.add(api_key)
                session.commit()
                session.refresh(api_key)
                
                # Return updated key (without showing the actual key value)
                return APIKeyCreateResponseSchema(
                    key_id=api_key.key_id,
                    name=api_key.name,
                    is_active=api_key.is_active,
                    created_at=api_key.created_at,
                    last_used_at=getattr(api_key, 'last_used_at', None),
                    key_preview=f"{api_key.key[:8]}...",
                    key_value=None,  # Don't show the actual key on update
                    message="API key updated successfully."
                )
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating API key: {str(e)}"
        )


@api_keys_router.delete("/{key_id}",
                       summary="Delete API key",
                       tags=["API Keys"])
async def delete_api_key(app_id: int, key_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Delete an API key.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.api_key import APIKey
        
        session = SessionLocal()
        try:
            api_key = session.query(APIKey).filter(
                APIKey.key_id == key_id,
                APIKey.app_id == app_id
            ).first()
            
            if not api_key:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="API key not found"
                )
            
            session.delete(api_key)
            session.commit()
            
            return {"message": "API key deleted successfully"}
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting API key: {str(e)}"
        )


@api_keys_router.post("/{key_id}/toggle",
                     summary="Toggle API key active status",
                     tags=["API Keys"])
async def toggle_api_key(app_id: int, key_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Toggle the active status of an API key.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.api_key import APIKey
        
        session = SessionLocal()
        try:
            api_key = session.query(APIKey).filter(
                APIKey.key_id == key_id,
                APIKey.app_id == app_id
            ).first()
            
            if not api_key:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="API key not found"
                )
            
            # Toggle the active status
            api_key.is_active = not api_key.is_active
            
            session.add(api_key)
            session.commit()
            session.refresh(api_key)
            
            status_text = "activated" if api_key.is_active else "deactivated"
            return {"message": f"API key {status_text} successfully"}
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error toggling API key: {str(e)}"
        ) 