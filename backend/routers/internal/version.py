from fastapi import APIRouter, Depends
from typing import Dict
import toml
from pathlib import Path

version_router = APIRouter()

def get_project_root() -> Path:
    """Get the project root directory where pyproject.toml is located."""
    return Path(__file__).parent.parent.parent.parent

def get_version() -> str:
    """Get the current version from pyproject.toml."""
    try:
        pyproject_path = get_project_root() / "pyproject.toml"
        with open(pyproject_path, "r") as f:
            pyproject = toml.load(f)
            return pyproject["project"]["version"]
    except Exception as e:
        return "unknown"

def get_version_info() -> Dict[str, str]:
    """Get detailed version information."""
    try:
        pyproject_path = get_project_root() / "pyproject.toml"
        with open(pyproject_path, "r") as f:
            pyproject = toml.load(f)
            return {
                "version": pyproject["project"]["version"],
                "name": pyproject["project"]["name"]
            }
    except Exception as e:
        return {
            "version": "unknown",
            "name": "ai-core-tools"
        }

@version_router.get("/version", 
                   summary="Get application version",
                   tags=["System"])
async def get_app_version():
    """
    Get the current application version from pyproject.toml.
    """
    return get_version_info() 