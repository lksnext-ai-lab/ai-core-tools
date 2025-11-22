from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict
import toml
from pathlib import Path

from services.version_service import VersionService
from schemas.version_schemas import (
    VersionResponseSchema, 
    VersionBumpRequestSchema, 
    VersionBumpResponseSchema
)
from utils.version_bumper import VersionBumperError
from utils.logger import get_logger

logger = get_logger(__name__)

PYPROJECT_TOML = "pyproject.toml"
version_router = APIRouter()

# Dependency to get VersionService instance
def get_version_service() -> VersionService:
    """Dependency to get VersionService instance"""
    return VersionService()

def get_project_root() -> Path:
    """Get the project root directory where pyproject.toml is located."""
    # Try multiple possible locations for pyproject.toml
    current_path = Path(__file__)
    
    # First, try the standard relative path (4 levels up)
    standard_path = current_path.parent.parent.parent.parent
    if (standard_path / PYPROJECT_TOML).exists():
        return standard_path
    
    # For Docker containers, try current working directory
    cwd_path = Path.cwd()
    if (cwd_path / PYPROJECT_TOML).exists():
        return cwd_path
    
    # Try one level up from current working directory
    parent_path = cwd_path.parent
    if (parent_path / PYPROJECT_TOML).exists():
        return parent_path
    
    # Try root directory (for Docker containers)
    root_path = Path("/")
    if (root_path / PYPROJECT_TOML).exists():
        return root_path
    
    # Fallback to standard path
    return standard_path

def get_version() -> str:
    """Get the current version from pyproject.toml."""
    try:
        pyproject_path = get_project_root() / PYPROJECT_TOML
        print(f"Trying to read version from: {pyproject_path}")
        print(f"File exists: {pyproject_path.exists()}")
        print(f"Current working directory: {Path.cwd()}")
        
        with open(pyproject_path, "r") as f:
            pyproject = toml.load(f)
            # Support both Poetry and PEP 621 formats
            if "tool" in pyproject and "poetry" in pyproject["tool"]:
                version = pyproject["tool"]["poetry"]["version"]
                print(f"Found version: {version}")
                return version
            elif "project" in pyproject:
                version = pyproject["project"]["version"]
                print(f"Found version: {version}")
                return version
            else:
                print("No version found in pyproject.toml")
                return "unknown"
    except Exception as e:
        print(f"Error reading version: {e}")
        return "unknown"

def get_version_info() -> Dict[str, str]:
    """Get detailed version information."""
    try:
        pyproject_path = get_project_root() / PYPROJECT_TOML
        print(f"Trying to read version info from: {pyproject_path}")
        
        with open(pyproject_path, "r") as f:
            pyproject = toml.load(f)
            # Support both Poetry and PEP 621 formats
            if "tool" in pyproject and "poetry" in pyproject["tool"]:
                result = {
                    "version": pyproject["tool"]["poetry"]["version"],
                    "name": pyproject["tool"]["poetry"]["name"]
                }
                print(f"Found version info: {result}")
                return result
            elif "project" in pyproject:
                result = {
                    "version": pyproject["project"]["version"],
                    "name": pyproject["project"]["name"]
                }
                print(f"Found version info: {result}")
                return result
            else:
                print("No version info found in pyproject.toml")
                return {
                    "version": "unknown",
                    "name": "ai-core-tools"
                }
    except Exception as e:
        print(f"Error reading version info: {e}")
        return {
            "version": "unknown",
            "name": "ai-core-tools"
        }

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

