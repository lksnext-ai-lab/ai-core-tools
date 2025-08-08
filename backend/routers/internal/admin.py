from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from typing import List, Optional
from db.database import SessionLocal
from models.user import User
from models.app import App
from models.agent import Agent
from models.api_key import APIKey
from services.user_service import UserService
from utils.config import is_omniadmin
from routers.auth import verify_jwt_token
from pydantic import BaseModel
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class UserListResponse(BaseModel):
    users: List[dict]
    total: int
    page: int
    per_page: int
    total_pages: int


class UserDetailResponse(BaseModel):
    user_id: int
    email: str
    name: Optional[str]
    created_at: str
    owned_apps_count: int
    api_keys_count: int
    is_active: bool


class SystemStatsResponse(BaseModel):
    total_users: int
    total_apps: int
    total_agents: int
    total_api_keys: int
    active_api_keys: int
    inactive_api_keys: int
    recent_users: List[dict]
    users_with_apps: int


async def get_current_user_oauth(request: Request):
    """
    Get current authenticated user using Google OAuth JWT tokens.
    Compatible with the frontend auth system.
    """
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please provide Authorization header with Bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = auth_header.split(' ')[1]
        
        # Verify token using Google OAuth system
        payload = verify_jwt_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return payload
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in authentication: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_admin(current_user: dict = Depends(get_current_user_oauth)):
    """Dependency to require admin access"""
    if not is_omniadmin(current_user.get('email')):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Users per page"),
    search: Optional[str] = Query(None, description="Search query for name or email"),
    current_user: dict = Depends(require_admin)
):
    """List all users with pagination and optional search"""
    try:
        if search:
            users, total = UserService.search_users(search, page, per_page)
        else:
            users, total = UserService.get_all_users(page, per_page)
        
        total_pages = (total + per_page - 1) // per_page
        
        return UserListResponse(
            users=users,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving users: {str(e)}")


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user(
    user_id: int,
    current_user: dict = Depends(require_admin)
):
    """Get detailed user information"""
    try:
        user = UserService.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return UserDetailResponse(
            user_id=user.user_id,
            email=user.email,
            name=user.name,
            created_at=user.created_at.isoformat(),
            owned_apps_count=len(user.owned_apps) if user.owned_apps else 0,
            api_keys_count=len(user.api_keys) if user.api_keys else 0,
            is_active=user.is_active
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving user: {str(e)}")


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: dict = Depends(require_admin)
):
    """Delete a user and all associated data"""
    try:
        user = UserService.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        success = UserService.delete_user(user_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete user")
        
        return {"message": f"User {user.email} and all associated data have been deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting user: {str(e)}")


@router.get("/stats", response_model=SystemStatsResponse)
async def get_system_stats(
    current_user: dict = Depends(require_admin)
):
    """Get system-wide statistics"""
    try:
        # Get user stats
        user_stats = UserService.get_user_stats()
        
        # Get other counts using SessionLocal
        session = SessionLocal()
        try:
            total_apps = session.query(App).count()
            total_agents = session.query(Agent).count()
            total_api_keys = session.query(APIKey).count()
            active_api_keys = session.query(APIKey).filter(APIKey.is_active == True).count()
        finally:
            session.close()
        
        return SystemStatsResponse(
            total_users=user_stats['total_users'],
            total_apps=total_apps,
            total_agents=total_agents,
            total_api_keys=total_api_keys,
            active_api_keys=active_api_keys,
            inactive_api_keys=total_api_keys - active_api_keys,
            recent_users=user_stats['recent_users'],
            users_with_apps=user_stats['users_with_apps']
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving system stats: {str(e)}") 