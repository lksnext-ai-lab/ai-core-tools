import toml
from pathlib import Path
from typing import Dict, Optional
import os

def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent

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
    return {
        "version": get_version(),
        "name": "ia-core-tools"
    }

# Version information as module-level variables
VERSION = get_version()
VERSION_INFO = get_version_info() 
APP_PATH = str(get_project_root() / "xxxx" / os.getcwd())   