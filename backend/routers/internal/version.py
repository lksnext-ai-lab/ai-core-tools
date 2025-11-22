from fastapi import APIRouter, Depends, HTTPException, status

from services.version_service import VersionService
from schemas.version_schemas import (
    VersionResponseSchema, 
    VersionBumpRequestSchema, 
    VersionBumpResponseSchema
)
from utils.version_bumper import VersionBumperError
from utils.logger import get_logger

logger = get_logger(__name__)

version_router = APIRouter()

# Dependency to get VersionService instance
def get_version_service() -> VersionService:
    """Dependency to get VersionService instance"""
    return VersionService()

@version_router.get("/", 
                   summary="Get application version",
                   tags=["System"],
                   response_model=VersionResponseSchema)
async def get_app_version(
    version_service: VersionService = Depends(get_version_service)
):
    """
    Get the current application version from pyproject.toml.
    Public endpoint - no authentication required.
    """
    try:
        return version_service.get_current_version()
    except VersionBumperError as e:
        logger.error(f"Failed to get version: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read version: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@version_router.post("/bump",
                    summary="Bump application version",
                    tags=["System"],
                    response_model=VersionBumpResponseSchema,
                    status_code=status.HTTP_200_OK)
async def bump_app_version(
    request: VersionBumpRequestSchema,
    version_service: VersionService = Depends(get_version_service)
):
    """
    Bump the application version in pyproject.toml.
    
    This endpoint allows you to bump the semantic version according to the specified type:
    - **patch**: For backward-compatible bug fixes (0.3.7 -> 0.3.8)
    - **minor**: For new backward-compatible features (0.3.7 -> 0.4.0)
    - **major**: For incompatible API changes (0.3.7 -> 1.0.0)
    
    Requires authentication and appropriate permissions.
    """
    try:
        result = version_service.bump_version(request.bump_type)
        
        return VersionBumpResponseSchema(
            old_version=result["old_version"],
            new_version=result["new_version"],
            message=f"Version successfully bumped from {result['old_version']} to {result['new_version']}"
        )
        
    except ValueError as e:
        logger.error(f"Invalid request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except VersionBumperError as e:
        logger.error(f"Failed to bump version: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to bump version: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

