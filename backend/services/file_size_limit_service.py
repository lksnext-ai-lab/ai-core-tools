"""
File size limit service for validating uploaded files against app limits.
Provides utilities for checking file sizes and generating appropriate error messages.
"""
from typing import Optional, Tuple
from fastapi import UploadFile
from utils.logger import get_logger

logger = get_logger(__name__)


class FileSizeLimitService:
    """
    Service for validating file sizes against app-specific limits.
    """
    
    @staticmethod
    def validate_file_size(
        file: UploadFile, 
        max_size_mb: int, 
        app_id: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate file size against app configuration.
        
        Args:
            file: The uploaded file
            max_size_mb: Maximum file size in MB (0 means no limit)
            app_id: Application ID for logging
            
        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if file is within limit or no limit set
            - error_message: Error message if file is too large, None if valid
        """
        if max_size_mb <= 0:
            # No limit configured
            logger.debug(f"No file size limit configured for app {app_id}")
            return True, None
            
        # Get file size
        if hasattr(file, 'size') and file.size is not None:
            file_size_bytes = file.size
        else:
            # If size not available, try to get it from file content
            try:
                current_position = file.file.tell()
                file.file.seek(0, 2)  # Seek to end
                file_size_bytes = file.file.tell()
                file.file.seek(current_position)  # Restore position
            except Exception as e:
                logger.warning(f"Could not determine file size for {file.filename}: {str(e)}")
                # If we can't determine size, allow the upload
                return True, None
        
        file_size_mb = file_size_bytes / (1024 * 1024)
        
        if file_size_mb > max_size_mb:
            error_msg = (
                f"File '{file.filename}' exceeds maximum size limit. "
                f"File size: {file_size_mb:.2f}MB, Maximum allowed: {max_size_mb}MB"
            )
            logger.warning(f"File size limit exceeded for app {app_id}: {error_msg}")
            return False, error_msg
            
        logger.debug(f"File size validation passed for app {app_id}: {file_size_mb:.2f}MB / {max_size_mb}MB")
        return True, None
    
    @staticmethod
    def get_file_size_mb(file: UploadFile) -> Optional[float]:
        """
        Get the size of a file in megabytes.
        
        Args:
            file: The uploaded file
            
        Returns:
            File size in MB or None if size cannot be determined
        """
        try:
            if hasattr(file, 'size') and file.size is not None:
                file_size_bytes = file.size
            else:
                current_position = file.file.tell()
                file.file.seek(0, 2)
                file_size_bytes = file.file.tell()
                file.file.seek(current_position)
            
            return file_size_bytes / (1024 * 1024)
        except Exception as e:
            logger.error(f"Error getting file size for {file.filename}: {str(e)}")
            return None
    
    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """
        Format file size in human-readable format.
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            Formatted string (e.g., "1.5 MB", "256 KB")
        """
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"


# Global instance
file_size_limit_service = FileSizeLimitService()
