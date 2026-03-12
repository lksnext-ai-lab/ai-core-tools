from fastapi import HTTPException, Depends, status
from fastapi.security.api_key import APIKeyHeader
from typing import Optional, Callable
from pydantic import BaseModel

from db.database import SessionLocal
from services.public_auth_service import PublicAuthService

# API Key authentication using header
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)
public_auth_service = PublicAuthService()

class APIKeyAuth(BaseModel):
    """API Key authentication result"""
    app_id: int
    api_key: str
    key_id: int

def create_api_key_dependency(app_id: int) -> Callable:
    """
    Create an API key dependency for a specific app_id.
    This is a dependency factory that returns a dependency function.
    """
    def get_api_key_auth(api_key: Optional[str] = Depends(api_key_header)) -> APIKeyAuth:
        """
        Authenticate API requests using API key.
        
        Args:
            api_key: The API key from the X-API-KEY header
            
        Returns:
            APIKeyAuth object with authentication details
            
        Raises:
            HTTPException: If authentication fails
        """
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required. Please provide X-API-KEY header."
            )
        
        session = SessionLocal()
        try:
            api_key_obj = public_auth_service.validate_api_key_for_app(session, app_id, api_key)
            
            return APIKeyAuth(
                app_id=app_id,
                api_key=api_key,
                key_id=api_key_obj.key_id
            )
        
        finally:
            session.close()
    
    return get_api_key_auth

# Simple function for when we have app_id available in the endpoint
def get_api_key_auth(api_key: Optional[str] = Depends(api_key_header)):
    """
    Simple API key authentication that returns the key without app validation.
    App validation happens in the endpoint logic.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Please provide X-API-KEY header."
        )
    return api_key

def validate_api_key_for_app(app_id: int, api_key: str) -> APIKeyAuth:
    """
    Validate API key for a specific app.
    
    Args:
        app_id: The app ID to validate against
        api_key: The API key to validate
        
    Returns:
        APIKeyAuth object with authentication details
        
    Raises:
        HTTPException: If authentication fails
    """
    session = SessionLocal()
    try:
        api_key_obj = public_auth_service.validate_api_key_for_app(session, app_id, api_key)
        
        return APIKeyAuth(
            app_id=app_id,
            api_key=api_key,
            key_id=api_key_obj.key_id
        )
    
    finally:
        session.close() 