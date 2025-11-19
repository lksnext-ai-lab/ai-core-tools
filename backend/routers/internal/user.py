"""
User endpoints for getting current user information.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from lks_idprovider.models.auth import AuthContext
from db.database import get_db
from services.user_service import UserService
from utils.config import is_omniadmin
from utils.logger import get_logger
from .auth_utils import get_current_user_oauth

logger = get_logger(__name__)

router = APIRouter(tags=["user"])


class CurrentUserResponse(BaseModel):
    """Response for current user info"""
    user_id: int
    email: str
    name: str
    is_admin: bool
    is_omniadmin: bool


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Get current user info",
    description="Get information about the currently authenticated user, including admin status",
)
async def get_current_user(
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
):
    """
    Get current user information including admin privileges.
    
    This endpoint works with both OIDC and development mode authentication.
    Returns user details including omniadmin status.
    
    Args:
        auth_context: Authentication context from token
        db: Database session
        
    Returns:
        User information with admin flags
    """
    user_email = auth_context.identity.email
    user = UserService.get_user_by_email(db, user_email)
    
    if not user:
        logger.error(f"User not found in database: {user_email}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in database",
        )
    
    return CurrentUserResponse(
        user_id=user.user_id,
        email=user.email,
        name=user.name or "",
        is_admin=is_omniadmin(user.email),
        is_omniadmin=is_omniadmin(user.email),
    )
