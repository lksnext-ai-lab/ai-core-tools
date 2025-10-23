"""
Origin validation dependency for public API endpoints.
Enforces per-app CORS origin restrictions based on app configuration.
"""
from fastapi import HTTPException, Depends, Request, status
from sqlalchemy.orm import Session

from models.app import App
from db.database import get_db
from services.origins_service import origins_service
from utils.logger import get_logger

logger = get_logger(__name__)


async def enforce_allowed_origins(
    app_id: int,
    request: Request,
    db: Session = Depends(get_db)
) -> None:
    """
    FastAPI dependency to enforce allowed origins for per-app CORS validation.
    
    Args:
        app_id: The app identifier from the URL path
        request: FastAPI request object to check origin header
        db: Database session
        
    Raises:
        HTTPException: 403 if origin is not allowed
    """
    try:
        # Load app to get allowed origins
        app = db.query(App).filter(App.app_id == app_id).first()
        if not app:
            logger.warning(f"App {app_id} not found for origin validation")
            return
        
        # Get the origin from the request headers
        origin = request.headers.get("origin")
        
        # Validate origin using the service
        validation_result = origins_service.validate_origin(
            origin=origin or "",
            allowed_origins=app.agent_cors_origins or ""
        )
        
        if not validation_result.is_allowed:
            logger.warning(f"Origin '{origin}' not allowed for app {app_id}. Allowed origins: {app.agent_cors_origins}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=validation_result.error_message or f"Origin '{origin}' is not allowed. Contact the application administrator to add your domain to the allowed origins list.",
                headers={
                    "X-CORS-Error": "Origin not allowed",
                    "X-App-ID": str(app_id),
                    "X-Origin-Received": origin or "none"
                }
            )
        
        if validation_result.matched_pattern:
            logger.debug(f"Origin '{origin}' allowed for app {app_id} (matched pattern: {validation_result.matched_pattern})")
        else:
            logger.debug(f"Origin '{origin}' allowed for app {app_id} (open CORS or no origin header)")
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 403)
        raise
    except Exception as e:
        # Log other errors but don't block the request
        logger.error(f"Error in origin validation for app {app_id}: {str(e)}")
        # Continue without origin validation on errors