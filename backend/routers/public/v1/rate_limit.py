"""
Rate limiting dependency for public API endpoints.
Enforces per-app agent execution limits using in-memory counters.
"""
from fastapi import HTTPException, Depends, Response, status
from sqlalchemy.orm import Session
from typing import Optional

from models.app import App
from db.database import get_db
from services.rate_limit_service import rate_limit_service
from utils.logger import get_logger

logger = get_logger(__name__)


async def enforce_app_rate_limit(
    app_id: int,
    response: Response,
    db: Session = Depends(get_db)
) -> None:
    """
    FastAPI dependency to enforce per-app rate limiting.
    
    Args:
        app_id: The app identifier from the URL path
        response: FastAPI response object to set headers
        db: Database session
        
    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    try:
        # Load app to get rate limit
        app = db.query(App).filter(App.app_id == app_id).first()
        if not app:
            logger.warning(f"App {app_id} not found for rate limiting")
            return
        
        rate_limit = app.agent_rate_limit or 0
        
        # If rate limit is 0 or negative, allow unlimited requests
        if rate_limit <= 0:
            # Set headers to indicate unlimited
            response.headers["X-RateLimit-Limit"] = "0"
            response.headers["X-RateLimit-Remaining"] = "-1"
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
            return
        
        # Check and consume rate limit
        state = rate_limit_service.check_and_consume(app_id, rate_limit)
        
        # Set rate limit headers
        response.headers["X-RateLimit-Limit"] = str(state.limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, state.remaining))
        response.headers["X-RateLimit-Reset"] = str(state.reset_epoch)
        
        # If rate limit exceeded, raise 429
        if state.remaining == 0:
            retry_after = state.reset_epoch - int(time.time())
            retry_after = max(1, retry_after)  # At least 1 second
            
            logger.info(f"Rate limit exceeded for app {app_id}: {rate_limit} requests per minute")
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {rate_limit} requests per minute allowed.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(state.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(state.reset_epoch)
                }
            )
        
        logger.debug(f"Rate limit check passed for app {app_id}: {state.remaining} remaining")
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 429)
        raise
    except Exception as e:
        # Log other errors but don't block the request
        logger.error(f"Error in rate limiting for app {app_id}: {str(e)}")
        # Continue without rate limiting on errors


# Import time for the dependency
import time
