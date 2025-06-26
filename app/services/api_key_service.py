from typing import List, Optional
import secrets
import string
from datetime import datetime
from extensions import db
from model.api_key import APIKey
from model.app import App
from utils.logger import get_logger
from utils.error_handlers import (
    handle_database_errors, NotFoundError, ValidationError, 
    AuthorizationError, validate_required_fields
)
from utils.database import safe_db_execute

logger = get_logger(__name__)


class APIKeyService:
    
    @staticmethod
    def generate_api_key(length: int = 48) -> str:
        """
        Generate a secure random API key
        
        Args:
            length: Length of the API key to generate
            
        Returns:
            Generated API key string
        """
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    @handle_database_errors("get_api_keys_by_app")
    def get_api_keys_by_app(app_id: int, user_id: int) -> List[APIKey]:
        """
        Get all API keys for a specific app and user
        
        Args:
            app_id: ID of the app
            user_id: ID of the user (for authorization)
            
        Returns:
            List of API keys
            
        Raises:
            ValidationError: If parameters are invalid
            AuthorizationError: If user doesn't have access to the app
        """
        if not app_id or not user_id:
            raise ValidationError("App ID and User ID are required")
        
        # Verify user has access to the app
        APIKeyService._verify_app_access(app_id, user_id)
        
        def query_operation():
            return db.session.query(APIKey).filter_by(app_id=app_id).all()
        
        api_keys = safe_db_execute(query_operation, "get_api_keys_by_app")
        logger.info(f"Retrieved {len(api_keys)} API keys for app {app_id}")
        return api_keys
    
    @staticmethod
    @handle_database_errors("create_api_key")
    def create_api_key(name: str, app_id: int, user_id: int) -> APIKey:
        """
        Create a new API key
        
        Args:
            name: Name for the API key
            app_id: ID of the app
            user_id: ID of the user
            
        Returns:
            Created API key
            
        Raises:
            ValidationError: If parameters are invalid
            AuthorizationError: If user doesn't have access to the app
        """
        # Validate inputs
        validate_required_fields(
            {'name': name, 'app_id': app_id, 'user_id': user_id},
            ['name', 'app_id', 'user_id']
        )
        
        name = name.strip()
        if not name:
            raise ValidationError("API key name cannot be empty")
        
        # Verify user has access to the app
        APIKeyService._verify_app_access(app_id, user_id)
        
        def create_operation():
            api_key = APIKey(
                key=APIKeyService.generate_api_key(),
                name=name,
                app_id=app_id,
                user_id=user_id,
                created_at=datetime.now(),
                is_active=True
            )
            db.session.add(api_key)
            db.session.flush()  # Get the ID
            return api_key
        
        api_key = safe_db_execute(create_operation, "create_api_key")
        logger.info(f"Created API key '{name}' for app {app_id} by user {user_id}")
        return api_key
    
    @staticmethod
    @handle_database_errors("delete_api_key")
    def delete_api_key(key_id: int, user_id: int) -> bool:
        """
        Delete an API key
        
        Args:
            key_id: ID of the API key to delete
            user_id: ID of the user (for authorization)
            
        Returns:
            True if deleted successfully
            
        Raises:
            NotFoundError: If API key not found
            AuthorizationError: If user doesn't own the API key
        """
        api_key = APIKeyService._get_api_key_with_auth(key_id, user_id)
        
        def delete_operation():
            db.session.delete(api_key)
            db.session.flush()
            return True
        
        result = safe_db_execute(delete_operation, "delete_api_key")
        logger.info(f"Deleted API key {key_id} for user {user_id}")
        return result
    
    @staticmethod
    @handle_database_errors("toggle_api_key")
    def toggle_api_key(key_id: int, user_id: int) -> APIKey:
        """
        Toggle API key active status
        
        Args:
            key_id: ID of the API key to toggle
            user_id: ID of the user (for authorization)
            
        Returns:
            Updated API key
            
        Raises:
            NotFoundError: If API key not found
            AuthorizationError: If user doesn't own the API key
        """
        api_key = APIKeyService._get_api_key_with_auth(key_id, user_id)
        
        def toggle_operation():
            api_key.is_active = not api_key.is_active
            api_key.updated_at = datetime.now()
            db.session.add(api_key)
            db.session.flush()
            return api_key
        
        updated_key = safe_db_execute(toggle_operation, "toggle_api_key")
        status = 'activated' if updated_key.is_active else 'deactivated'
        logger.info(f"API key {key_id} {status} for user {user_id}")
        return updated_key
    
    @staticmethod
    def _verify_app_access(app_id: int, user_id: int) -> App:
        """
        Verify that user has access to the specified app
        
        Args:
            app_id: ID of the app
            user_id: ID of the user
            
        Returns:
            App instance if access is granted
            
        Raises:
            NotFoundError: If app not found
            AuthorizationError: If user doesn't have access
        """
        def query_operation():
            return db.session.query(App).filter_by(app_id=app_id).first()
        
        app = safe_db_execute(query_operation, "verify_app_access")
        
        if not app:
            raise NotFoundError(f"App with ID {app_id} not found", "app")
        
        if app.owner_id != user_id:
            raise AuthorizationError(f"User {user_id} does not have access to app {app_id}")
        
        return app
    
    @staticmethod
    def _get_api_key_with_auth(key_id: int, user_id: int) -> APIKey:
        """
        Get API key with authorization check
        
        Args:
            key_id: ID of the API key
            user_id: ID of the user
            
        Returns:
            API key instance
            
        Raises:
            NotFoundError: If API key not found
            AuthorizationError: If user doesn't own the API key
        """
        def query_operation():
            return db.session.query(APIKey).filter_by(key_id=key_id).first()
        
        api_key = safe_db_execute(query_operation, "get_api_key_with_auth")
        
        if not api_key:
            raise NotFoundError(f"API key with ID {key_id} not found", "api_key")
        
        if api_key.user_id != user_id:
            raise AuthorizationError(f"User {user_id} does not own API key {key_id}")
        
        return api_key
    
    @staticmethod
    @handle_database_errors("delete_by_app_id")
    def delete_by_app_id(app_id: int):
        """Delete all API keys for a specific app"""
        def delete_operation():
            deleted_count = db.session.query(APIKey).filter(APIKey.app_id == app_id).delete()
            db.session.flush()
            return deleted_count
        
        count = safe_db_execute(delete_operation, "delete_by_app_id")
        logger.info(f"Deleted {count} API keys for app {app_id}")
        return count
