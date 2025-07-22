from typing import List, Optional
import secrets
import string
from datetime import datetime
from db.session import SessionLocal
from models.api_key import APIKey
from models.app import App
from utils.logger import get_logger
from utils.error_handlers import (
    handle_database_errors, NotFoundError, ValidationError, 
    AuthorizationError, validate_required_fields
)

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
        
        session = SessionLocal()
        try:
            api_keys = session.query(APIKey).filter_by(app_id=app_id).all()
            logger.info(f"Retrieved {len(api_keys)} API keys for app {app_id}")
            return api_keys
        finally:
            session.close()
    
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
        
        session = SessionLocal()
        try:
            api_key = APIKey(
                key=APIKeyService.generate_api_key(),
                name=name,
                app_id=app_id,
                user_id=user_id,
                created_at=datetime.now(),
                is_active=True
            )
            session.add(api_key)
            session.flush()  # Get the ID
            session.commit()
            logger.info(f"Created API key '{name}' for app {app_id} by user {user_id}")
            return api_key
        finally:
            session.close()
    
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
        
        session = SessionLocal()
        try:
            session.delete(api_key)
            session.flush()
            session.commit()
            logger.info(f"Deleted API key {key_id} for user {user_id}")
            return True
        finally:
            session.close()
    
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
        session = SessionLocal()
        try:
            app = session.query(App).filter_by(app_id=app_id).first()
            
            if not app:
                raise NotFoundError(f"App with ID {app_id} not found", "app")
            
            if app.owner_id != user_id:
                raise AuthorizationError(f"User {user_id} does not have access to app {app_id}")
            
            return app
        finally:
            session.close()
    
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
        session = SessionLocal()
        try:
            api_key = session.query(APIKey).filter_by(key_id=key_id).first()
            
            if not api_key:
                raise NotFoundError(f"API key with ID {key_id} not found", "api_key")
            
            if api_key.user_id != user_id:
                raise AuthorizationError(f"User {user_id} does not own API key {key_id}")
            
            return api_key
        finally:
            session.close()
    
    @staticmethod
    @handle_database_errors("delete_by_app_id")
    def delete_by_app_id(app_id: int):
        """Delete all API keys for a specific app"""
        session = SessionLocal()
        try:
            deleted_count = session.query(APIKey).filter(APIKey.app_id == app_id).delete()
            session.flush()
            session.commit()
            logger.info(f"Deleted {deleted_count} API keys for app {app_id}")
            return deleted_count
        finally:
            session.close() 