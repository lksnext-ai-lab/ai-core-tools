"""Internal API endpoint for per-agent rate-limit usage."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Annotated

from db.database import get_db
from services.app_service import AppService
from services.rate_limit_service import rate_limit_service
from schemas.apps_schemas import AgentRateLimitUsageSchema
from routers.controls.role_authorization import AppRole, require_min_role
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "/{app_id}",
    response_model=List[AgentRateLimitUsageSchema],
    responses={
        404: {"description": "App not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_agent_usage_stats(
    app_id: int,
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role(AppRole.VIEWER))],
) -> List[AgentRateLimitUsageSchema]:
    """
    Get the current rate-limit usage for each active agent in an app.

    Args:
        app_id: The app identifier

    Returns:
        Per-agent rate-limit usage statistics
    """
    try:
        # Get app
        app = AppService(db).get_app(app_id)
        if not app:
            raise HTTPException(
                status_code=404,
                detail=f"App {app_id} not found"
            )

        usage = rate_limit_service.get_app_agent_usage_stats(
            app.app_id, app.agent_rate_limit or 0
        )
        logger.debug(
            "Retrieved rate-limit usage for %s agents in app %s", len(usage), app_id
        )
        return [AgentRateLimitUsageSchema(**item) for item in usage]

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving agent usage for app %s: %s", app_id, str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve agent usage statistics"
        )
