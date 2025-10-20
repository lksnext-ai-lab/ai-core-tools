"""
File size limit dependency for public API endpoints.
Enforces per-app file size limits for file uploads.
"""
from fastapi import HTTPException, Depends, status, UploadFile, Request
from sqlalchemy.orm import Session
from typing import List, Optional

from models.app import App
from db.database import get_db
from services.file_size_limit_service import file_size_limit_service
from utils.logger import get_logger

logger = get_logger(__name__)


async def enforce_file_size_limit(
    app_id: int,
    request: Request,
    db: Session = Depends(get_db)
) -> None:
    """
    FastAPI dependency to enforce per-app file size limits.
    Validates the total request payload size using Content-Length header.
    
    Args:
        app_id: The app identifier from the URL path
        request: FastAPI request object
        db: Database session
        
    Raises:
        HTTPException: 413 Payload Too Large if request exceeds limit
    """
    try:
        # Load app to get file size limit
        app = db.query(App).filter(App.app_id == app_id).first()
        if not app:
            logger.warning(f"App {app_id} not found for file size validation")
            return
        
        max_file_size_mb = app.max_file_size_mb or 0
        
        # If limit is 0 or negative, allow unlimited file sizes
        if max_file_size_mb <= 0:
            logger.debug(f"No file size limit configured for app {app_id}")
            return
        
        # Get Content-Length from headers
        content_length = request.headers.get('content-length')
        if not content_length:
            logger.debug(f"No Content-Length header found for app {app_id}, skipping validation")
            return
        
        try:
            content_length_bytes = int(content_length)
        except ValueError:
            logger.warning(f"Invalid Content-Length header for app {app_id}: {content_length}")
            return
        
        # Convert to MB
        content_length_mb = content_length_bytes / (1024 * 1024)
        max_total_mb = max_file_size_mb * 10  # Allow up to 10 files at max size
        
        # Check if total payload exceeds reasonable limit
        if content_length_mb > max_total_mb:
            logger.info(f"Total payload size exceeded for app {app_id}: {content_length_mb:.2f}MB > {max_total_mb}MB")
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Total upload size ({content_length_mb:.2f}MB) exceeds maximum allowed ({max_total_mb}MB). Maximum {max_file_size_mb}MB per file, up to 10 files."
            )
        
        logger.debug(f"File size pre-validation passed for app {app_id}: {content_length_mb:.2f}MB / {max_total_mb}MB")
        
        # Store the limit in request state for per-file validation in the endpoint
        request.state.max_file_size_mb = max_file_size_mb
        request.state.app_id_for_file_validation = app_id
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 413)
        raise
    except Exception as e:
        # Log other errors but don't block the request
        logger.error(f"Error in file size validation for app {app_id}: {str(e)}")
        # Continue without validation on errors


async def validate_files_size(
    files: List[UploadFile],
    max_size_mb: int,
    app_id: int
) -> None:
    """
    Validate file sizes and raise exception if any file exceeds limit.
    This should be called within the endpoint after files are received.
    
    Args:
        files: List of uploaded files
        max_size_mb: Maximum file size in MB
        app_id: Application ID for logging
        
    Raises:
        HTTPException: 413 if any file exceeds limit
    """
    if max_size_mb <= 0:
        return
    
    failed_files = []
    for file in files:
        is_valid, error_msg = file_size_limit_service.validate_file_size(
            file, max_size_mb, app_id
        )
        
        if not is_valid:
            failed_files.append({
                'filename': file.filename,
                'error': error_msg
            })
    
    if failed_files:
        logger.info(f"File size limit exceeded for app {app_id}: {len(failed_files)} file(s)")
        
        # Create detailed error message
        error_details = "; ".join([f"{f['filename']}: {f['error']}" for f in failed_files])
        
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size limit exceeded. Maximum {max_size_mb}MB per file allowed. Failed files: {error_details}"
        )


def get_app_file_size_limit(app_id: int, db: Session = Depends(get_db)) -> int:
    """
    Helper function to get app file size limit.
    
    Args:
        app_id: The app identifier
        db: Database session
        
    Returns:
        Maximum file size in MB (0 = unlimited)
    """
    try:
        app = db.query(App).filter(App.app_id == app_id).first()
        if not app:
            return 0
        return app.max_file_size_mb or 0
    except Exception as e:
        logger.error(f"Error getting file size limit for app {app_id}: {str(e)}")
        return 0
