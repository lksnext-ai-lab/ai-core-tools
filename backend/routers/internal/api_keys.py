from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional

# Import services
from services.api_key_service import APIKeyService

# Import schemas and auth
from .schemas import *
from .auth import get_current_user

api_keys_router = APIRouter()

# ==================== API KEY MANAGEMENT ====================

@api_keys_router.get("/", 
                    summary="List API keys",
                    tags=["API Keys"],
                    response_model=List[APIKeyListItemSchema])
async def list_api_keys(app_id: int, current_user: dict = Depends(get_current_user)):
    """
    List all API keys for a specific app.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Get API keys using the service
        api_keys = APIKeyService.get_api_keys_by_app(app_id, user_id)
        
        result = []
        for api_key in api_keys:
            result.append(APIKeyListItemSchema(
                key_id=api_key.key_id,
                name=api_key.name,
                is_active=api_key.is_active,
                created_at=api_key.create_date,
                last_used_at=getattr(api_key, 'last_used_at', None),
                # Don't expose the actual key value for security
                key_preview=f"{api_key.key[:8]}..." if api_key.key else "***"
            ))
        
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving API keys: {str(e)}"
        )


@api_keys_router.get("/{key_id}",
                    summary="Get API key details",
                    tags=["API Keys"],
                    response_model=APIKeyDetailSchema)
async def get_api_key(app_id: int, key_id: int, current_user: dict = Depends(get_current_user)):
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
                created_at=api_key.create_date,
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
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new API key or update an existing one.
    When creating, the actual key value is returned once for security.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        if key_id == 0:
            # Create new API key
            api_key = APIKeyService.create_api_key(
                name=api_key_data.name,
                app_id=app_id,
                user_id=user_id
            )
            
            return APIKeyCreateResponseSchema(
                key_id=api_key.key_id,
                name=api_key.name,
                is_active=api_key.is_active,
                created_at=api_key.create_date,
                last_used_at=getattr(api_key, 'last_used_at', None),
                key_preview=f"{api_key.key[:8]}...",
                # Return the actual key only once upon creation
                key_value=api_key.key,
                message="API key created successfully. Save this key securely - it won't be shown again!"
            )
        else:
            # Update existing API key (name and active status only)
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
                
                # Update fields
                api_key.name = api_key_data.name
                if hasattr(api_key_data, 'is_active'):
                    api_key.is_active = api_key_data.is_active
                
                session.commit()
                session.refresh(api_key)
                
                return APIKeyCreateResponseSchema(
                    key_id=api_key.key_id,
                    name=api_key.name,
                    is_active=api_key.is_active,
                    created_at=api_key.create_date,
                    last_used_at=getattr(api_key, 'last_used_at', None),
                    key_preview=f"{api_key.key[:8]}...",
                    key_value=None,  # Don't return key on update
                    message="API key updated successfully"
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
async def delete_api_key(app_id: int, key_id: int, current_user: dict = Depends(get_current_user)):
    """
    Delete an API key. This action cannot be undone.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Delete API key using the service
        APIKeyService.delete_api_key(key_id, user_id)
        
        return {"message": "API key deleted successfully"}
        
    except Exception as e:
        # Check if it's a not found error
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error deleting API key: {str(e)}"
            )


@api_keys_router.post("/{key_id}/toggle",
                     summary="Toggle API key active status",
                     tags=["API Keys"])
async def toggle_api_key(app_id: int, key_id: int, current_user: dict = Depends(get_current_user)):
    """
    Toggle the active status of an API key (enable/disable).
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
            
            # Toggle active status
            api_key.is_active = not api_key.is_active
            session.commit()
            
            status_text = "enabled" if api_key.is_active else "disabled"
            return {"message": f"API key {status_text} successfully", "is_active": api_key.is_active}
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error toggling API key status: {str(e)}"
        ) 