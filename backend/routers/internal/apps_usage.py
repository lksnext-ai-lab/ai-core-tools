"""
API endpoints for authenticated users to read accessible app usage statistics.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Annotated
from lks_idprovider.models.auth import AuthContext

from db.database import get_db
from services.app_service import AppService
from services.rate_limit_service import rate_limit_service
from routers.controls.role_authorization import AppRole, require_min_role
from .auth_utils import get_current_user_oauth
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/", responses={500: {"description": "Internal server error"}})
async def get_apps_usage_stats(
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
) -> List[Dict[str, Any]]:
    """
    Get usage statistics for apps accessible to the authenticated user.
    
    Returns:
        List of accessible app usage statistics with stress metrics
    """
    try:
        user_id = int(auth_context.identity.id)
        apps = AppService(db).get_apps(user_id)
        
        usage_stats = []
        
        for app in apps:
            # Get usage statistics from rate limit service
            stats = rate_limit_service.get_app_usage_stats(
                app.app_id, 
                app.agent_rate_limit or 0
            )
            
            # Add app information
            app_stats = {
                'app_id': app.app_id,
                'app_name': app.name,
                'agent_rate_limit': app.agent_rate_limit or 0,
                **stats
            }
            
            usage_stats.append(app_stats)
        
        logger.debug(f"Retrieved usage stats for {len(usage_stats)} apps")
        return usage_stats
        
    except Exception as e:
        logger.error(f"Error retrieving app usage stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve app usage statistics"
        )


@router.get("/{app_id}", responses={404: {"description": "App not found"}, 500: {"description": "Internal server error"}})
async def get_app_usage_stats(
    app_id: int, 
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role(AppRole.VIEWER))],
) -> Dict[str, Any]:
    """
    Get usage statistics for a specific app.
    
    Args:
        app_id: The app identifier
        
    Returns:
        App usage statistics with stress metrics
    """
    try:
        # Get app
        app = AppService(db).get_app(app_id)
        if not app:
            raise HTTPException(
                status_code=404,
                detail=f"App {app_id} not found"
            )
        
        # Get usage statistics
        stats = rate_limit_service.get_app_usage_stats(
            app.app_id, 
            app.agent_rate_limit or 0
        )
        
        # Add app information
        app_stats = {
            'app_id': app.app_id,
            'app_name': app.name,
            'agent_rate_limit': app.agent_rate_limit or 0,
            **stats
        }
        
        logger.debug(f"Retrieved usage stats for app {app_id}")
        return app_stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving usage stats for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve app usage statistics"
        )
