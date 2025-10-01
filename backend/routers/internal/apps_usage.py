"""
API endpoint to get app usage statistics and stress levels.
Provides real-time rate limiting metrics for admin dashboard.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from models.app import App
from db.database import get_db
from services.rate_limit_service import rate_limit_service
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/")
async def get_apps_usage_stats(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """
    Get usage statistics for all apps to display stress levels.
    
    Returns:
        List of app usage statistics with stress metrics
    """
    try:
        # Get all apps with their rate limits
        apps = db.query(App).all()
        
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


@router.get("/{app_id}")
async def get_app_usage_stats(
    app_id: int, 
    db: Session = Depends(get_db)
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
        app = db.query(App).filter(App.app_id == app_id).first()
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
