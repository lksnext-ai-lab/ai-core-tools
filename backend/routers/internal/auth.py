"""
Authentication endpoints for development mode.

This router provides endpoints for development authentication that bypass OIDC.
These endpoints are only available when OIDC_ENABLED is false.
"""

import os
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.database import get_db
from services.user_service import UserService
from utils.dev_auth import generate_dev_token
from utils.logger import get_logger

logger = get_logger(__name__)

# Check if OIDC authentication is enabled (dev mode when false)
OIDC_ENABLED = os.getenv('OIDC_ENABLED', 'true').lower() == 'true'

router = APIRouter(tags=["auth"])


class DevLoginRequest(BaseModel):
    """Request body for dev login"""
    email: str


class DevLoginResponse(BaseModel):
    """Response for successful dev login"""
    access_token: str
    expires_at: str
    token_type: str
    user: dict


@router.post(
    "/dev-login",
    response_model=DevLoginResponse,
    summary="Development mode login",
    description=(
        "Authenticate using email only (development mode). "
        "Only works when OIDC_ENABLED=false and email exists in database."
    ),
)
async def dev_login(
    request: DevLoginRequest,
    db: Session = Depends(get_db),
):
    """
    Development mode authentication endpoint.
    
    This endpoint allows login with just an email address for development/testing.
    It bypasses OIDC authentication and generates a simple JWT token.
    
    Security constraints:
    - Only enabled when OIDC_ENABLED=false
    - User email must already exist in the database
    - Does not create new users (security boundary)
    
    Args:
        request: Login request with email
        db: Database session
        
    Returns:
        JWT token and user information
        
    Raises:
        HTTPException 503: If development mode is disabled
        HTTPException 401: If user email not found in database
    """
    # Security check: Only allow in development mode (OIDC disabled)
    if OIDC_ENABLED:
        logger.warning(
            "Dev login attempted while OIDC_ENABLED is true"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Development login is not available. "
                "This endpoint only works when OIDC_ENABLED is false."
            ),
        )
    
    email = request.email.lower()
    
    # Security check: User must exist in database
    # This prevents arbitrary user creation and enforces pre-seeding
    user = UserService.get_user_by_email(db, email)
    
    if not user:
        logger.warning(
            "Dev login failed: email not found in database."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "User not found. Only existing users can authenticate in "
                "dev mode. Please ensure your email is in the database."
            ),
        )
    
    # Check if user is active
    if hasattr(user, "is_active") and not user.is_active:
        logger.warning(
            f"Dev login failed: inactive user attempted login: {email}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated.",
        )
    
    # Generate development JWT token
    token_data = generate_dev_token(email=email, name=user.name)
    
    logger.info("Dev login successful.")
    
    # Return token and user info
    return DevLoginResponse(
        access_token=token_data["access_token"],
        expires_at=token_data["expires_at"],
        token_type=token_data["token_type"],
        user={
            "user_id": user.user_id,
            "email": user.email,
            "name": user.name,
        },
    )
