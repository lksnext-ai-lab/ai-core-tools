from fastapi import APIRouter
from typing import Dict
import toml
from pathlib import Path


PYPROJECT_TOML = "pyproject.toml"
version_router = APIRouter()

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
                   tags=["System"])
async def get_app_version():
    """
    Get the current application version from pyproject.toml.
    Public endpoint - no authentication required.
    """
    return get_version_info()

@version_router.get("/config", 
                   summary="Get system configuration",
                   tags=["System"])
async def get_system_config():
    """
    Get system configuration including vector database type.
    Public endpoint - no authentication required.
    
    Returns:
        - vector_db_type: Type of vector database (PGVECTOR or QDRANT)
    """
    from backend.config import VECTOR_DB_TYPE
    
    return {
        "vector_db_type": VECTOR_DB_TYPE
    } 