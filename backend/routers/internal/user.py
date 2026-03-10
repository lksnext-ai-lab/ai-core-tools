"""
User endpoints for getting current user information.
"""

from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File
import os
import glob
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from lks_idprovider.models.auth import AuthContext
from db.database import get_db
from services.user_service import UserService
from utils.config import is_omniadmin, get_app_config
from utils.logger import get_logger
from .auth_utils import get_current_user_oauth

logger = get_logger(__name__)

ALLOWED_MIME_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
MAX_AVATAR_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB

router = APIRouter(tags=["user"])


class CurrentUserResponse(BaseModel):
    """Response for current user info"""
    user_id: int
    email: str
    name: str
    is_admin: bool
    is_omniadmin: bool
    avatar_url: Optional[str] = None


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
    
    avatar_url = f"/public/avatars/{user.user_id}" if user.avatar_path else None

    return CurrentUserResponse(
        user_id=user.user_id,
        email=user.email,
        name=user.name or "",
        is_admin=is_omniadmin(user.email),
        is_omniadmin=is_omniadmin(user.email),
        avatar_url=avatar_url,
    )


@router.post(
    "/me/avatar",
    response_model=CurrentUserResponse,
    summary="Upload or replace avatar",
    description="Upload a profile avatar image (JPEG, PNG, WebP, GIF). Max 2 MB. Replaces any existing avatar.",
)
async def upload_avatar(
    file: UploadFile = File(...),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
):
    user_email = auth_context.identity.email
    user = UserService.get_user_by_email(db, user_email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Validate MIME type
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{content_type}'. Allowed: {', '.join(ALLOWED_MIME_TYPES)}",
        )

    # Read and check size
    contents = await file.read()
    if len(contents) > MAX_AVATAR_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 2 MB.",
        )

    # Resolve storage path
    app_config = get_app_config()
    tmp_base = app_config.get("TMP_BASE_FOLDER", "data/tmp")
    avatars_dir = os.path.join(tmp_base, "avatars")
    os.makedirs(avatars_dir, exist_ok=True)

    # Delete any existing avatar files for this user (all extensions)
    for old_file in glob.glob(os.path.join(avatars_dir, f"{user.user_id}.*")):
        try:
            os.remove(old_file)
        except OSError:
            logger.warning(f"Could not remove old avatar file: {old_file}")

    # Write new file — extension derived from MIME type, NOT from user filename
    ext = ALLOWED_MIME_TYPES[content_type]
    relative_path = f"avatars/{user.user_id}.{ext}"
    full_path = os.path.join(tmp_base, relative_path)
    with open(full_path, "wb") as f:
        f.write(contents)

    # Persist path
    try:
        UserService.update_avatar_path(db, user.user_id, relative_path)
    except Exception as e:
        # Clean up file if DB update fails
        try:
            os.remove(full_path)
        except OSError:
            pass
        logger.error(f"Failed to update avatar_path for user {user.user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save avatar")

    # Re-fetch updated user
    user = UserService.get_user_by_email(db, user_email)
    avatar_url = f"/public/avatars/{user.user_id}" if user.avatar_path else None
    return CurrentUserResponse(
        user_id=user.user_id,
        email=user.email,
        name=user.name or "",
        is_admin=is_omniadmin(user.email),
        is_omniadmin=is_omniadmin(user.email),
        avatar_url=avatar_url,
    )


@router.delete(
    "/me/avatar",
    response_model=CurrentUserResponse,
    summary="Remove avatar",
    description="Remove the current user's avatar image.",
)
async def delete_avatar(
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
):
    user_email = auth_context.identity.email
    user = UserService.get_user_by_email(db, user_email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Remove file from disk if it exists
    if user.avatar_path:
        app_config = get_app_config()
        tmp_base = app_config.get("TMP_BASE_FOLDER", "data/tmp")
        full_path = os.path.join(tmp_base, user.avatar_path)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except OSError:
                logger.warning(f"Could not remove avatar file: {full_path}")

    UserService.clear_avatar(db, user.user_id)

    return CurrentUserResponse(
        user_id=user.user_id,
        email=user.email,
        name=user.name or "",
        is_admin=is_omniadmin(user.email),
        is_omniadmin=is_omniadmin(user.email),
        avatar_url=None,
    )
