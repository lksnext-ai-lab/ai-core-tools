from fastapi import HTTPException, status, Request, Depends
from sqlalchemy.orm import Session
from routers.auth import verify_jwt_token
from db.database import get_db
from services.user_service import UserService
from utils.logger import get_logger

logger = get_logger(__name__)

async def get_current_user_oauth(request: Request, db: Session = Depends(get_db)):
    """
    Get current authenticated user using Google OAuth JWT tokens.
    Compatible with the frontend auth system.
    
    This is a shared utility function used across all internal routers.
    """
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        logger.debug(f"Auth header received: {auth_header[:20] + '...' if auth_header and len(auth_header) > 20 else auth_header}")
        
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.error("No Authorization header or invalid format")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please provide Authorization header with Bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = auth_header.split(' ')[1]
        logger.debug(f"Token extracted: {token[:20] + '...' if len(token) > 20 else token}")
        
        # Verify token using Google OAuth system
        payload = verify_jwt_token(token)
        if not payload:
            logger.error("Token verification failed - invalid or expired token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check if user is active
        user_email = payload.get('email')
        if user_email:
            user = UserService.get_user_by_email(db, user_email)
            if user and hasattr(user, 'is_active') and not user.is_active:
                logger.warning(f"Inactive user attempted to access: {user_email}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your account has been deactivated. Please contact support for assistance.",
                )
        
        logger.debug(f"Token verified successfully for user: {payload.get('user_id')}")
        return payload
        
    except HTTPException:
        logger.error("HTTPException in authentication, re-raising")
        raise
    except Exception as e:
        logger.error(f"Error in authentication: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        ) 