"""
User endpoints for getting current user information.
"""
from datetime import datetime
from typing import Annotated, List, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query, UploadFile, File, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from lks_idprovider.models.auth import AuthContext
from db.database import get_db
from models.user import User
from services.user_service import UserService
from services.stored_image_service import StoredImageService
from utils.config import is_omniadmin
from utils.logger import get_logger
from .auth_utils import get_current_user_oauth
from .stored_image_endpoints import (
    IMAGE_GET_RESPONSES,
    IMAGE_UPLOAD_DESCRIPTION,
    ImageUpdatedResponse,
    delete_image,
    image_response,
    store_uploaded_image,
)

logger = get_logger(__name__)

router = APIRouter(tags=["user"])


class CurrentUserResponse(BaseModel):
    """Response for current user info"""
    user_id: int
    email: str
    name: str
    is_admin: bool
    platform_role: str
    # Version of the profile picture (GET /me/avatar); null = no picture, show initials.
    avatar_updated_at: Optional[datetime] = None


def _get_db_user(auth_context: AuthContext, db: Session) -> User:
    user = UserService.get_user_by_email(db, auth_context.identity.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found in database")
    return user


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
        avatar_updated_at=StoredImageService.user_avatars(db).get_updated_at(user.user_id),
    )


@router.get(
    "/me/avatar",
    summary="Get my profile picture",
    description="Pass `v` (the `avatar_updated_at` of /me) to get a response the browser may cache.",
    response_class=Response,
    responses=IMAGE_GET_RESPONSES,
)
async def get_my_avatar(
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    v: Annotated[Optional[str], Query(max_length=64)] = None,
):
    user = _get_db_user(auth_context, db)
    return image_response(StoredImageService.user_avatars(db), user.user_id, v)


@router.put(
    "/me/avatar",
    response_model=ImageUpdatedResponse,
    summary="Upload my profile picture",
    description=IMAGE_UPLOAD_DESCRIPTION,
)
async def upload_my_avatar(
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
):
    user = _get_db_user(auth_context, db)
    updated_at = await store_uploaded_image(StoredImageService.user_avatars(db), user.user_id, file)
    return ImageUpdatedResponse(image_updated_at=updated_at)


@router.delete(
    "/me/avatar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove my profile picture",
)
async def delete_my_avatar(
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    user = _get_db_user(auth_context, db)
    return delete_image(StoredImageService.user_avatars(db), user.user_id)


class UserSearchResultItem(BaseModel):
    user_id: int
    name: str
    email: str
    platform_role: str
    is_omniadmin: bool = False


@router.get(
    "/users/search",
    response_model=List[UserSearchResultItem],
    summary="Search platform users",
    description="Search users by name or email. Used for collaboration invitations.",
)
async def search_users(
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str, Query(min_length=1, description="Search query (name or email)")],
):
    current_email = auth_context.identity.email
    users, _ = UserService.search_users(db, q, page=1, per_page=10)
    return [
        UserSearchResultItem(
            user_id=u["user_id"],
            name=u.get("name") or "",
            email=u["email"],
            platform_role=u.get("platform_role") or "editor",
            is_omniadmin=u.get("is_omniadmin", False),
        )
        for u in users
        if u["email"] != current_email
    ]


@router.get(
    "/users/omniadmins",
    response_model=List[UserSearchResultItem],
    summary="List protected omniadmin accounts",
    description="List platform users configured as omniadmins. Used to surface protected "
                "accounts in the collaboration invite UI without requiring a search.",
)
async def list_omniadmin_accounts(
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    current_email = auth_context.identity.email
    users = UserService.get_omniadmin_accounts(db)
    return [
        UserSearchResultItem(
            user_id=u["user_id"],
            name=u.get("name") or "",
            email=u["email"],
            platform_role=u.get("platform_role") or "editor",
            is_omniadmin=u.get("is_omniadmin", False),
        )
        for u in users
        if u["email"] != current_email
    ]
