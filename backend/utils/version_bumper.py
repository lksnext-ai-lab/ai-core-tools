"""
Utility functions for semantic version bumping.
Provides functionality to read, parse, and update version numbers in pyproject.toml.
"""
import toml
from pathlib import Path
from typing import Dict, Tuple, Optional
from enum import Enum

class BumpType(str, Enum):
    """Type of version bump to perform"""
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"

class VersionBumperError(Exception):
    """Base exception for version bumper errors"""
    pass

class InvalidVersionError(VersionBumperError):
    """Raised when version format is invalid"""
    pass

class ProjectFileNotFoundError(VersionBumperError):
    """Raised when pyproject.toml is not found"""
    pass

def get_project_root() -> Path:
    """
    Get the project root directory where pyproject.toml is located.
    
    Returns:
        Path: The project root directory
    """
    # Start from this file and go up to find pyproject.toml
    current_path = Path(__file__)
    
    # Try going up from backend/utils/
    standard_path = current_path.parent.parent.parent
    if (standard_path / "pyproject.toml").exists():
        return standard_path
    
    # Try current working directory
    cwd_path = Path.cwd()
    if (cwd_path / "pyproject.toml").exists():
        return cwd_path
    
    # Fallback to standard path
    return standard_path

def parse_version(version_str: str) -> Tuple[int, int, int]:
    """
    Parse a semantic version string into its components.
    
    Args:
        version_str: Version string in format "MAJOR.MINOR.PATCH"
        
    Returns:
        Tuple of (major, minor, patch) as integers
        
    Raises:
        InvalidVersionError: If version format is invalid
    """
    try:
        parts = version_str.split('.')
        if len(parts) != 3:
            raise InvalidVersionError(
                f"Version must have exactly 3 parts (MAJOR.MINOR.PATCH), got: {version_str}"
            )
        
        major, minor, patch = [int(p) for p in parts]
        
        if major < 0 or minor < 0 or patch < 0:
            raise InvalidVersionError(
                f"Version parts must be non-negative, got: {version_str}"
            )
        
        return (major, minor, patch)
    except ValueError as e:
        raise InvalidVersionError(
            f"Invalid version format, must be numeric: {version_str}"
        ) from e

def format_version(major: int, minor: int, patch: int) -> str:
    """
    Format version components into a semantic version string.
    
    Args:
        major: Major version number
        minor: Minor version number
        patch: Patch version number
        
    Returns:
        Version string in format "MAJOR.MINOR.PATCH"
    """
    return f"{major}.{minor}.{patch}"

def bump_version(current_version: str, bump_type: BumpType) -> str:
    """
    Bump a semantic version according to the specified bump type.
    
    Args:
        current_version: Current version string
        bump_type: Type of bump (major, minor, or patch)
        
    Returns:
        New version string after bumping
        
    Raises:
        InvalidVersionError: If current version format is invalid
    """
    major, minor, patch = parse_version(current_version)
    
    if bump_type == BumpType.MAJOR:
        major += 1
        minor = 0
        patch = 0
    elif bump_type == BumpType.MINOR:
        minor += 1
        patch = 0
    elif bump_type == BumpType.PATCH:
        patch += 1
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")
    
    return format_version(major, minor, patch)

def read_current_version() -> str:
    """
    Read the current version from pyproject.toml.
    
    Returns:
        Current version string
        
    Raises:
        ProjectFileNotFoundError: If pyproject.toml is not found
        InvalidVersionError: If version is not found in pyproject.toml
    """
    try:
        pyproject_path = get_project_root() / "pyproject.toml"
        
        if not pyproject_path.exists():
            raise ProjectFileNotFoundError(
                f"pyproject.toml not found at {pyproject_path}"
            )
        
        with open(pyproject_path, "r") as f:
            pyproject = toml.load(f)
        
        # Try Poetry format first
        if "tool" in pyproject and "poetry" in pyproject["tool"]:
            if "version" in pyproject["tool"]["poetry"]:
                return pyproject["tool"]["poetry"]["version"]
        
        # Try PEP 621 format
        if "project" in pyproject and "version" in pyproject["project"]:
            return pyproject["project"]["version"]
        
        raise InvalidVersionError(
            "Version not found in pyproject.toml. Expected either "
            "[tool.poetry].version or [project].version"
        )
        
    except toml.TomlDecodeError as e:
        raise InvalidVersionError(
            f"Failed to parse pyproject.toml: {str(e)}"
        ) from e

def write_new_version(new_version: str) -> None:
    """
    Write a new version to pyproject.toml.
    
    Args:
        new_version: New version string to write
        
    Raises:
        ProjectFileNotFoundError: If pyproject.toml is not found
        InvalidVersionError: If version location is not found in pyproject.toml
    """
    try:
        pyproject_path = get_project_root() / "pyproject.toml"
        
        if not pyproject_path.exists():
            raise ProjectFileNotFoundError(
                f"pyproject.toml not found at {pyproject_path}"
            )
        
        with open(pyproject_path, "r") as f:
            pyproject = toml.load(f)
        
        # Update version in appropriate location(s)
        # Note: If both Poetry and PEP 621 formats exist, both are updated
        # to maintain consistency. This is the expected behavior for projects
        # that support multiple packaging tools.
        version_updated = False
        
        if "tool" in pyproject and "poetry" in pyproject["tool"]:
            if "version" in pyproject["tool"]["poetry"]:
                pyproject["tool"]["poetry"]["version"] = new_version
                version_updated = True
        
        if "project" in pyproject and "version" in pyproject["project"]:
            pyproject["project"]["version"] = new_version
            version_updated = True
        
        if not version_updated:
            raise InvalidVersionError(
                "Version location not found in pyproject.toml. Expected either "
                "[tool.poetry].version or [project].version"
            )
        
        # Write back to file
        with open(pyproject_path, "w") as f:
            toml.dump(pyproject, f)
            
    except toml.TomlDecodeError as e:
        raise InvalidVersionError(
            f"Failed to parse pyproject.toml: {str(e)}"
        ) from e

def bump_project_version(bump_type: BumpType) -> Dict[str, str]:
    """
    Bump the project version in pyproject.toml.
    
    Args:
        bump_type: Type of version bump (major, minor, or patch)
        
    Returns:
        Dictionary with old_version and new_version
        
    Raises:
        VersionBumperError: If any error occurs during version bumping
    """
    try:
        # Read current version
        current_version = read_current_version()
        
        # Calculate new version
        new_version = bump_version(current_version, bump_type)
        
        # Write new version
        write_new_version(new_version)
        
        return {
            "old_version": current_version,
            "new_version": new_version
        }
        
    except Exception as e:
        if isinstance(e, VersionBumperError):
            raise
        raise VersionBumperError(f"Unexpected error during version bump: {str(e)}") from e
