"""
Database session management utilities
"""
from contextlib import contextmanager
from typing import Any, Callable, Optional, TypeVar, Generator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from extensions import db
from utils.logger import get_logger
from utils.error_handlers import DatabaseError, safe_execute

logger = get_logger(__name__)

T = TypeVar('T')


@contextmanager
def safe_db_session() -> Generator[Session, None, None]:
    """
    Context manager for safe database session handling
    
    Yields:
        Database session
        
    Raises:
        DatabaseError: If database operation fails
    """
    session = db.session
    try:
        yield session
        session.commit()
        logger.debug("Database transaction committed successfully")
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error, rolling back transaction: {str(e)}", exc_info=True)
        raise DatabaseError(f"Database operation failed: {str(e)}")
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error, rolling back transaction: {str(e)}", exc_info=True)
        raise


def safe_db_execute(operation: Callable[[], T], operation_name: str = None) -> T:
    """
    Safely execute a database operation with automatic session management
    
    Args:
        operation: Function to execute (should use db.session)
        operation_name: Optional name for logging
        
    Returns:
        Result of the operation
        
    Raises:
        DatabaseError: If database operation fails
    """
    op_name = operation_name or operation.__name__
    logger.debug(f"Executing database operation: {op_name}")
    
    try:
        with safe_db_session():
            result = operation()
            logger.debug(f"Database operation '{op_name}' completed successfully")
            return result
    except DatabaseError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in database operation '{op_name}': {str(e)}", exc_info=True)
        raise DatabaseError(f"Database operation '{op_name}' failed: {str(e)}")


def safe_db_get(model_class, model_id: int, operation_name: str = None) -> Optional[Any]:
    """
    Safely get a model instance by ID
    
    Args:
        model_class: SQLAlchemy model class
        model_id: ID of the instance to retrieve
        operation_name: Optional name for logging
        
    Returns:
        Model instance or None if not found
        
    Raises:
        DatabaseError: If database operation fails
    """
    op_name = operation_name or f"get_{model_class.__name__}"
    
    def get_operation():
        return db.session.query(model_class).filter(model_class.id == model_id).first()
    
    return safe_db_execute(get_operation, op_name)


def safe_db_get_by_field(model_class, field_name: str, field_value: Any, operation_name: str = None) -> Optional[Any]:
    """
    Safely get a model instance by field value
    
    Args:
        model_class: SQLAlchemy model class
        field_name: Name of the field to filter by
        field_value: Value to filter by
        operation_name: Optional name for logging
        
    Returns:
        Model instance or None if not found
        
    Raises:
        DatabaseError: If database operation fails
    """
    op_name = operation_name or f"get_{model_class.__name__}_by_{field_name}"
    
    def get_operation():
        field = getattr(model_class, field_name)
        return db.session.query(model_class).filter(field == field_value).first()
    
    return safe_db_execute(get_operation, op_name)


def safe_db_create(model_instance, operation_name: str = None) -> Any:
    """
    Safely create a new model instance
    
    Args:
        model_instance: Model instance to create
        operation_name: Optional name for logging
        
    Returns:
        Created model instance
        
    Raises:
        DatabaseError: If database operation fails
    """
    op_name = operation_name or f"create_{model_instance.__class__.__name__}"
    
    def create_operation():
        db.session.add(model_instance)
        db.session.flush()  # Flush to get the ID
        return model_instance
    
    return safe_db_execute(create_operation, op_name)


def safe_db_update(model_instance, updates: dict, operation_name: str = None) -> Any:
    """
    Safely update a model instance
    
    Args:
        model_instance: Model instance to update
        updates: Dictionary of field updates
        operation_name: Optional name for logging
        
    Returns:
        Updated model instance
        
    Raises:
        DatabaseError: If database operation fails
    """
    op_name = operation_name or f"update_{model_instance.__class__.__name__}"
    
    def update_operation():
        for field, value in updates.items():
            if hasattr(model_instance, field):
                setattr(model_instance, field, value)
            else:
                logger.warning(f"Field '{field}' not found in {model_instance.__class__.__name__}")
        
        db.session.add(model_instance)
        db.session.flush()
        return model_instance
    
    return safe_db_execute(update_operation, op_name)


def safe_db_delete(model_instance, operation_name: str = None) -> bool:
    """
    Safely delete a model instance
    
    Args:
        model_instance: Model instance to delete
        operation_name: Optional name for logging
        
    Returns:
        True if deleted successfully
        
    Raises:
        DatabaseError: If database operation fails
    """
    op_name = operation_name or f"delete_{model_instance.__class__.__name__}"
    
    def delete_operation():
        db.session.delete(model_instance)
        db.session.flush()
        return True
    
    return safe_db_execute(delete_operation, op_name)


def safe_db_bulk_create(model_instances: list, operation_name: str = None) -> list:
    """
    Safely create multiple model instances in bulk
    
    Args:
        model_instances: List of model instances to create
        operation_name: Optional name for logging
        
    Returns:
        List of created model instances
        
    Raises:
        DatabaseError: If database operation fails
    """
    if not model_instances:
        return []
    
    op_name = operation_name or f"bulk_create_{model_instances[0].__class__.__name__}"
    
    def bulk_create_operation():
        db.session.add_all(model_instances)
        db.session.flush()
        return model_instances
    
    return safe_db_execute(bulk_create_operation, op_name)


def safe_db_query(query_func: Callable[[], T], operation_name: str = None) -> T:
    """
    Safely execute a custom query function
    
    Args:
        query_func: Function that performs the query
        operation_name: Optional name for logging
        
    Returns:
        Query result
        
    Raises:
        DatabaseError: If database operation fails
    """
    op_name = operation_name or "custom_query"
    return safe_db_execute(query_func, op_name)


def check_db_connection() -> bool:
    """
    Check if database connection is working
    
    Returns:
        True if connection is working, False otherwise
    """
    try:
        with safe_db_session() as session:
            session.execute(db.text("SELECT 1"))
            logger.info("Database connection check successful")
            return True
    except Exception as e:
        logger.error(f"Database connection check failed: {str(e)}")
        return False 