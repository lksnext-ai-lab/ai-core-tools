"""
Authentication endpoints for development mode.

This router provides endpoints for development authentication that bypass OIDC.
These endpoints are only available when AICT_LOGIN is set to FAKE mode.
"""

import os
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from db.database import get_db
from services.user_service import UserService
from services.app_collaboration_service import AppCollaborationService
from utils.dev_auth import generate_dev_token
from utils.auth_config import AuthConfig
from utils.logger import get_logger
from lks_idprovider import AuthContext
from .auth_utils import get_current_user_oauth
from schemas.apps_schemas import InvitationResponseSchema

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


class PendingInvitationSchema(BaseModel):
    """Schema for pending invitations"""
    id: int
    app_id: int
    app_name: str
    inviter_email: str
    inviter_name: Optional[str]
    invited_at: datetime
    role: str


@router.get(
    "/pending-invitations",
    response_model=List[PendingInvitationSchema],
    summary="Get pending invitations",
    description="Get all pending collaboration invitations for the current user",
)
async def get_pending_invitations(
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
):
    """Get pending invitations for the current user"""
    user_id = auth_context.identity.id
    collaboration_service = AppCollaborationService(db)
    
    invitations = collaboration_service.get_user_pending_invitations(user_id)
    
    result = []
    for inv in invitations:
        result.append(PendingInvitationSchema(
            id=inv.id,
            app_id=inv.app_id,
            app_name=inv.app.name if inv.app else "Unknown App",
            inviter_email=inv.inviter.email if inv.inviter else "Unknown",
            inviter_name=inv.inviter.name if inv.inviter else "Unknown",
            invited_at=inv.invited_at,
            role=inv.role.value
        ))
    
    return result


@router.post(
    "/invitations/{invitation_id}/respond",
    summary="Respond to invitation",
    description="Accept or decline a collaboration invitation",
)
async def respond_to_invitation(
    invitation_id: int,
    response: InvitationResponseSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
):
    """Respond to a collaboration invitation"""
    user_id = auth_context.identity.id
    collaboration_service = AppCollaborationService(db)
    
    success = collaboration_service.respond_to_invitation(
        invitation_id, user_id, response.action
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to respond to invitation. It may not exist, belong to you, or be pending."
        )
    
    return {"success": True, "message": f"Invitation {response.action}ed successfully"}


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
