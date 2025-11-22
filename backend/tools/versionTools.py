"""
LangChain tools for version management.
Provides tools for reading and bumping semantic versions in the project.
"""
from langchain_core.tools import tool
from utils.version_bumper import (
    read_current_version,
    bump_project_version,
    BumpType,
    VersionBumperError
)
from utils.logger import get_logger

logger = get_logger(__name__)

@tool
def get_project_version() -> str:
    """
    Get the current project version from pyproject.toml.
    
    Returns:
        str: Current version in format MAJOR.MINOR.PATCH (e.g., "0.3.7")
        
    This tool is useful when you need to check the current version of the project
    before deciding whether to bump it or to report the current version.
    """
    try:
        version = read_current_version()
        logger.info(f"Retrieved current version: {version}")
        return version
    except VersionBumperError as e:
        error_msg = f"Failed to get project version: {str(e)}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Unexpected error getting project version: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg

@tool
def bump_version_major() -> str:
    """
    Bump the project version MAJOR number (X.0.0) in pyproject.toml.
    
    Returns:
        str: A message with the old and new version
        
    Use this tool when making incompatible API changes or major new features
    that break backward compatibility. For example:
    - 0.3.7 -> 1.0.0
    - 1.2.5 -> 2.0.0
    
    This resets minor and patch numbers to 0.
    """
    try:
        result = bump_project_version(BumpType.MAJOR)
        message = f"Version bumped from {result['old_version']} to {result['new_version']}"
        logger.info(message)
        return message
    except VersionBumperError as e:
        error_msg = f"Failed to bump major version: {str(e)}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Unexpected error bumping major version: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg

@tool
def bump_version_minor() -> str:
    """
    Bump the project version MINOR number (x.X.0) in pyproject.toml.
    
    Returns:
        str: A message with the old and new version
        
    Use this tool when adding new functionality in a backward-compatible manner.
    For example:
    - 0.3.7 -> 0.4.0
    - 1.2.5 -> 1.3.0
    
    This resets the patch number to 0.
    """
    try:
        result = bump_project_version(BumpType.MINOR)
        message = f"Version bumped from {result['old_version']} to {result['new_version']}"
        logger.info(message)
        return message
    except VersionBumperError as e:
        error_msg = f"Failed to bump minor version: {str(e)}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Unexpected error bumping minor version: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg

@tool
def bump_version_patch() -> str:
    """
    Bump the project version PATCH number (x.x.X) in pyproject.toml.
    
    Returns:
        str: A message with the old and new version
        
    Use this tool when making backward-compatible bug fixes. For example:
    - 0.3.7 -> 0.3.8
    - 1.2.5 -> 1.2.6
    
    This is the most common type of version bump for small fixes and improvements.
    """
    try:
        result = bump_project_version(BumpType.PATCH)
        message = f"Version bumped from {result['old_version']} to {result['new_version']}"
        logger.info(message)
        return message
    except VersionBumperError as e:
        error_msg = f"Failed to bump patch version: {str(e)}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Unexpected error bumping patch version: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg

# Export all tools as a list for easy registration
VERSION_TOOLS = [
    get_project_version,
    bump_version_major,
    bump_version_minor,
    bump_version_patch
]
