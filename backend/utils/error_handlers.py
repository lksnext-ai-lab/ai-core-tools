"""
Centralized error handling utilities for FastAPI
"""
import traceback
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple
from sqlalchemy.exc import SQLAlchemyError
from utils.logger import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base application error"""
    
    def __init__(self, message: str, error_code: str = None, status_code: int = 500):
        self.message = message
        self.error_code = error_code or 'GENERIC_ERROR'
        self.status_code = status_code
        super().__init__(self.message)


class ValidationError(AppError):
    """Validation error"""
    
    def __init__(self, message: str, field: str = None):
        self.field = field
        super().__init__(message, 'VALIDATION_ERROR', 400)


class DatabaseError(AppError):
    """Database operation error"""
    
    def __init__(self, message: str, operation: str = None):
        self.operation = operation
        super().__init__(message, 'DATABASE_ERROR', 500)


class AuthenticationError(AppError):
    """Authentication error"""
    
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, 'AUTH_ERROR', 401)


class AuthorizationError(AppError):
    """Authorization error"""
    
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, 'AUTHZ_ERROR', 403)


class NotFoundError(AppError):
    """Resource not found error"""
    
    def __init__(self, message: str, resource: str = None):
        self.resource = resource
        super().__init__(message, 'NOT_FOUND', 404)


def handle_database_errors(operation: str = None):
    """Decorator to handle database errors consistently"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except SQLAlchemyError as e:
                logger.error(f"Database error in {operation or func.__name__}: {str(e)}", exc_info=True)
                raise DatabaseError(f"Database operation failed: {str(e)}", operation)
            except Exception as e:
                logger.error(f"Unexpected error in {operation or func.__name__}: {str(e)}", exc_info=True)
                raise
        return wrapper
    return decorator


def handle_validation_errors(func):
    """Decorator to handle validation errors"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValidationError as e:
            logger.warning(f"Validation error in {func.__name__}: {str(e)}")
            raise
        except ValueError as e:
            logger.warning(f"Value error in {func.__name__}: {str(e)}")
            raise ValidationError(str(e))
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            raise
    return wrapper


def safe_execute(func: Callable, *args, default_return=None, log_errors: bool = True, **kwargs) -> Tuple[Any, Optional[Exception]]:
    """
    Safely execute a function and return result with any exception
    
    Args:
        func: Function to execute
        *args: Function arguments
        default_return: Value to return if function fails
        log_errors: Whether to log errors
        **kwargs: Function keyword arguments
    
    Returns:
        Tuple of (result, exception). Exception is None if successful.
    """
    try:
        result = func(*args, **kwargs)
        return result, None
    except Exception as e:
        if log_errors:
            logger.error(f"Error executing {func.__name__}: {str(e)}", exc_info=True)
        return default_return, e


def create_error_response(error: Exception, include_traceback: bool = False) -> Tuple[Dict[str, Any], int]:
    """
    Create a standardized error response
    
    Args:
        error: The exception that occurred
        include_traceback: Whether to include traceback (for debugging)
    
    Returns:
        Tuple of (response_dict, status_code)
    """
    if isinstance(error, AppError):
        response = {
            'error': error.message,
            'error_code': error.error_code,
            'status_code': error.status_code
        }
        status_code = error.status_code
    else:
        response = {
            'error': str(error),
            'error_code': 'INTERNAL_ERROR',
            'status_code': 500
        }
        status_code = 500
    
    if include_traceback:
        response['traceback'] = traceback.format_exc()
    
    return response, status_code


def validate_required_fields(data: dict, required_fields: list, raise_on_missing: bool = True) -> list:
    """
    Validate that required fields are present in data
    
    Args:
        data: Dictionary to validate
        required_fields: List of required field names
        raise_on_missing: Whether to raise exception on missing fields
    
    Returns:
        List of missing fields
    
    Raises:
        ValidationError: If fields are missing and raise_on_missing is True
    """
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]
    
    if missing_fields and raise_on_missing:
        raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")
    
    return missing_fields


def validate_field_types(data: dict, field_types: dict, raise_on_invalid: bool = True) -> list:
    """
    Validate field types in data
    
    Args:
        data: Dictionary to validate
        field_types: Dictionary mapping field names to expected types
        raise_on_invalid: Whether to raise exception on invalid types
    
    Returns:
        List of fields with invalid types
    
    Raises:
        ValidationError: If types are invalid and raise_on_invalid is True
    """
    invalid_fields = []
    
    for field, expected_type in field_types.items():
        if field in data and data[field] is not None:
            if not isinstance(data[field], expected_type):
                invalid_fields.append(f"{field} (expected {expected_type.__name__}, got {type(data[field]).__name__})")
    
    if invalid_fields and raise_on_invalid:
        raise ValidationError(f"Invalid field types: {', '.join(invalid_fields)}")
    
    return invalid_fields