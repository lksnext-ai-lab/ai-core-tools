from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from typing import Optional
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from db.database import get_db
from models.app import App
from models.agent import Agent
from models.api_key import APIKey
from services.user_service import UserService
from utils.config import is_omniadmin
from routers.internal.auth_utils import get_current_user_oauth
from schemas.admin_schemas import UserListResponse, UserDetailResponse, SystemStatsResponse
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["admin"])


def require_admin(auth_context: AuthContext = Depends(get_current_user_oauth)):
    """Dependency to require admin access"""
    if not is_omniadmin(auth_context.identity.email):
        raise HTTPException(status_code=403, detail="Admin access required")
    return auth_context


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Users per page"),
    search: Optional[str] = Query(None, description="Search query for name or email"),
    auth_context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all users with pagination and optional search"""
    try:
        if search:
            users, total = UserService.search_users(db, search, page, per_page)
        else:
            users, total = UserService.get_all_users(db, page, per_page)
        
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
    auth_context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get detailed user information"""
    try:
        user = UserService.get_user_by_id_with_relations(db, user_id)
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
    auth_context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a user and all associated data"""
    try:
        user = UserService.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        success = UserService.delete_user(db, user_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete user")
        
        return {"message": f"User {user.email} and all associated data have been deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting user: {str(e)}")


@router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: int,
    auth_context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Activate a user account"""
    try:
        user = UserService.activate_user(db, user_id, auth_context.identity.email)
        logger.info(f"User {user.email} activated by admin {auth_context.identity.email}")
        return {
            "message": f"User {user.email} has been activated successfully",
            "user_id": user.user_id,
            "is_active": user.is_active
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error activating user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error activating user: {str(e)}")


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    auth_context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Deactivate a user account"""
    try:
        user = UserService.deactivate_user(db, user_id, auth_context.identity.email)
        logger.info(f"User {user.email} deactivated by admin {auth_context.identity.email}")
        return {
            "message": f"User {user.email} has been deactivated successfully",
            "user_id": user.user_id,
            "is_active": user.is_active
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deactivating user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deactivating user: {str(e)}")


@router.get("/stats", response_model=SystemStatsResponse)
async def get_system_stats(
    auth_context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get system-wide statistics"""
    try:
        # Get user stats
        user_stats = UserService.get_user_stats(db)
        active_users = UserService.get_active_users_count(db)
        inactive_users = UserService.get_inactive_users_count(db)
        
        # Get other counts using the same db session
        total_apps = db.query(App).count()
        total_agents = db.query(Agent).count()
        total_api_keys = db.query(APIKey).count()
        active_api_keys = db.query(APIKey).filter(APIKey.is_active == True).count()
        
        return SystemStatsResponse(
            total_users=user_stats['total_users'],
            active_users=active_users,
            inactive_users=inactive_users,
            total_apps=total_apps,
            total_agents=total_agents,
            total_api_keys=total_api_keys,
            active_api_keys=active_api_keys,
            inactive_api_keys=total_api_keys - active_api_keys,
            recent_users=user_stats['recent_users_list'],
            users_with_apps=user_stats['users_with_apps']
        )
    except Exception as e:
        logger.error(f"Error retrieving system stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving system stats: {str(e)}") 