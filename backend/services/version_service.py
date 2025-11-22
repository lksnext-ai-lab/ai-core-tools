"""
Service for version management operations.
Provides business logic for version bumping and validation.
"""
from typing import Dict, Optional
from utils.version_bumper import (
    read_current_version,
    bump_project_version,
    BumpType,
    VersionBumperError
)
from utils.logger import get_logger

logger = get_logger(__name__)

class VersionService:
    """Service for managing project version operations"""
    
    def get_current_version(self) -> Dict[str, str]:
        """
        Get the current project version.
        
        Returns:
            Dictionary with version information
            
        Raises:
            VersionBumperError: If version cannot be read
        """
        try:
            version = read_current_version()
            logger.info(f"Retrieved current version: {version}")
            return {
                "version": version,
                "name": "ai-core-tools"
            }
        except VersionBumperError as e:
            logger.error(f"Failed to get version: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting version: {str(e)}", exc_info=True)
            raise VersionBumperError(f"Unexpected error: {str(e)}") from e
    
    def bump_version(self, bump_type: str) -> Dict[str, str]:
        """
        Bump the project version.
        
        Args:
            bump_type: Type of bump - 'major', 'minor', or 'patch'
            
        Returns:
            Dictionary with old_version and new_version
            
        Raises:
            ValueError: If bump_type is invalid
            VersionBumperError: If version cannot be bumped
        """
        # Validate bump_type
        valid_types = ['major', 'minor', 'patch']
        if bump_type.lower() not in valid_types:
            raise ValueError(
                f"Invalid bump_type: {bump_type}. Must be one of: {', '.join(valid_types)}"
            )
        
        try:
            # Convert string to BumpType enum
            bump_enum = BumpType(bump_type.lower())
            
            # Perform the bump
            result = bump_project_version(bump_enum)
            
            logger.info(
                f"Version bumped successfully: {result['old_version']} -> {result['new_version']}"
            )
            
            return result
            
        except VersionBumperError as e:
            logger.error(f"Failed to bump version: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error bumping version: {str(e)}", exc_info=True)
            raise VersionBumperError(f"Unexpected error: {str(e)}") from e
    
    def validate_version_format(self, version: str) -> bool:
        """
        Validate that a version string is in correct semantic version format.
        
        Args:
            version: Version string to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            from utils.version_bumper import parse_version
            parse_version(version)
            return True
        except Exception:
            return False
