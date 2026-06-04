"""
User endpoints for getting current user information.
"""
from typing import Annotated, List, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query
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
    platform_role: str


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Get current user info",
    description="Get information about the currently authenticated user, including admin status",
)
async def get_current_user(
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
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
        platform_role=user.platform_role or 'editor',
    )


class UserSearchResultItem(BaseModel):
    user_id: int
    name: str
    email: str
    platform_role: str


@router.get(
    "/users/search",
    response_model=List[UserSearchResultItem],
    summary="Search platform users",
    description="Search users by name or email. Used for collaboration invitations.",
)
async def search_users(
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str, Query(min_length=2, description="Search query (name or email)")],
):
    current_email = auth_context.identity.email
    users, _ = UserService.search_users(db, q, page=1, per_page=10)
    return [
        UserSearchResultItem(
            user_id=u["user_id"],
            name=u.get("name") or "",
            email=u["email"],
            platform_role=u.get("platform_role") or "editor",
        )
        for u in users
        if u["email"] != current_email
    ]
