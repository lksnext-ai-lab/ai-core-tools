"""
Authentication endpoints for development mode.

This router provides endpoints for development authentication that bypass OIDC.
These endpoints are only available when AICT_LOGIN is set to FAKE mode.
"""

import os
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.database import get_db
from services.user_service import UserService
from utils.dev_auth import generate_dev_token
from utils.auth_config import AuthConfig
from utils.logger import get_logger

logger = get_logger(__name__)

# Load authentication configuration
AuthConfig.load_config()

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
        "Only works when AICT_LOGIN=FAKE and email exists in database."
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
    - Only enabled when AICT_LOGIN=FAKE
    - User email must already exist in the database
    - Does not create new users (security boundary)
    
    Args:
        request: Login request with email
        db: Database session
        
    Returns:
        JWT token and user information
        
    Raises:
        HTTPException 503: If FAKE login mode is not enabled
        HTTPException 401: If user email not found in database
    """
    # Security check: Only allow in FAKE login mode
    if AuthConfig.LOGIN_MODE != "FAKE":
        logger.warning(
            f"Dev login attempted while AICT_LOGIN={AuthConfig.LOGIN_MODE}"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Development login is not available. "
                "This endpoint only works when AICT_LOGIN=FAKE in environment variables."
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
            "Dev login failed: inactive user attempted login."
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
