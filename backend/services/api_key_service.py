from typing import List, Optional
import secrets
import string
from datetime import datetime
from sqlalchemy.orm import Session
from models.api_key import APIKey
from repositories.api_key_repository import APIKeyRepository
from utils.logger import get_logger
from schemas.api_key_schemas import APIKeyListItemSchema, APIKeyDetailSchema, APIKeyCreateResponseSchema

logger = get_logger(__name__)


class APIKeyService:
    """Service class for API key business logic"""
    
    def __init__(self, api_key_repository: APIKeyRepository = None):
        self.api_key_repository = api_key_repository or APIKeyRepository()
    
    @staticmethod
    def generate_api_key(length: int = 32) -> str:
        """
        Generate a secure random API key
        
        Args:
            length: Length of the API key to generate
            
        Returns:
            Generated API key string
        """
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    def get_api_keys_list(self, db: Session, app_id: int) -> List[APIKeyListItemSchema]:
        """
        Get all API keys for a specific app as list items
        
        Args:
            db: Database session
            app_id: ID of the app
            
        Returns:
            List of API key list items
        """
        api_keys = self.api_key_repository.get_by_app_id(db, app_id)
        
        result = []
        for api_key in api_keys:
            result.append(APIKeyListItemSchema(
                key_id=api_key.key_id,
                name=api_key.name,
                is_active=api_key.is_active,
                created_at=api_key.created_at,
                last_used_at=getattr(api_key, 'last_used_at', None),
                key_preview=f"{api_key.key[:8]}..." if api_key.key else "***"
            ))
        
        logger.info(f"Retrieved {len(result)} API keys for app {app_id}")
        return result
    
    def get_api_key_detail(self, db: Session, app_id: int, key_id: int) -> Optional[APIKeyDetailSchema]:
        """
        Get detailed information about a specific API key
        
        Args:
            db: Database session
            app_id: ID of the app
            key_id: ID of the API key
            
        Returns:
            API key detail or None if not found
        """
        if key_id == 0:
            # New API key form
            return APIKeyDetailSchema(
                key_id=0,
                name="",
                is_active=True,
                created_at=None,
                last_used_at=None,
                key_preview="Will be generated on save"
            )
        
        api_key = self.api_key_repository.get_by_id_and_app(db, key_id, app_id)
        
        if not api_key:
            return None
        
        return APIKeyDetailSchema(
            key_id=api_key.key_id,
            name=api_key.name,
            is_active=api_key.is_active,
            created_at=api_key.created_at,
            last_used_at=getattr(api_key, 'last_used_at', None),
            key_preview=f"{api_key.key[:8]}..." if api_key.key else "***"
        )
    
    def create_api_key(self, db: Session, app_id: int, user_id: int, name: str, is_active: bool = True) -> APIKeyCreateResponseSchema:
        """
        Create a new API key
        
        Args:
            db: Database session
            app_id: ID of the app
            user_id: ID of the user
            name: Name for the API key
            is_active: Whether the key should be active
            
        Returns:
            Created API key response with actual key value
        """
        # Create API key entity
        api_key = APIKey()
        api_key.app_id = app_id
        api_key.user_id = user_id
        api_key.created_at = datetime.now()
        api_key.key = self.generate_api_key()
        api_key.name = name
        api_key.is_active = is_active
        
        # Save to database
        created_api_key = self.api_key_repository.create(db, api_key)
        
        logger.info(f"Created API key '{name}' for app {app_id} by user {user_id}")
        
        return APIKeyCreateResponseSchema(
            key_id=created_api_key.key_id,
            name=created_api_key.name,
            is_active=created_api_key.is_active,
            created_at=created_api_key.created_at,
            last_used_at=None,
            key_preview=f"{created_api_key.key[:8]}...",
            key_value=created_api_key.key,  # Show the actual key once
            message="API key created successfully. Please save this key as it won't be shown again."
        )
    
    def update_api_key(self, db: Session, app_id: int, key_id: int, name: str, is_active: bool) -> Optional[APIKeyCreateResponseSchema]:
        """
        Update an existing API key
        
        Args:
            db: Database session
            app_id: ID of the app
            key_id: ID of the API key
            name: New name for the API key
            is_active: Whether the key should be active
            
        Returns:
            Updated API key response or None if not found
        """
        api_key = self.api_key_repository.get_by_id_and_app(db, key_id, app_id)
        
        if not api_key:
            return None
        
        # Update fields
        api_key.name = name
        api_key.is_active = is_active
        
        # Save changes
        updated_api_key = self.api_key_repository.update(db, api_key)
        
        logger.info(f"Updated API key {key_id} for app {app_id}")
        
        return APIKeyCreateResponseSchema(
            key_id=updated_api_key.key_id,
            name=updated_api_key.name,
            is_active=updated_api_key.is_active,
            created_at=updated_api_key.created_at,
            last_used_at=getattr(updated_api_key, 'last_used_at', None),
            key_preview=f"{updated_api_key.key[:8]}...",
            key_value=None,  # Don't show the actual key on update
            message="API key updated successfully."
        )
    
    def delete_api_key(self, db: Session, app_id: int, key_id: int) -> bool:
        """
        Delete an API key
        
        Args:
            db: Database session
            app_id: ID of the app
            key_id: ID of the API key to delete
            
        Returns:
            True if deleted successfully, False if not found
        """
        api_key = self.api_key_repository.get_by_id_and_app(db, key_id, app_id)
        
        if not api_key:
            return False
        
        self.api_key_repository.delete(db, api_key)
        
        logger.info(f"Deleted API key {key_id} for app {app_id}")
        return True
    
    def toggle_api_key(self, db: Session, app_id: int, key_id: int) -> Optional[str]:
        """
        Toggle the active status of an API key
        
        Args:
            db: Database session
            app_id: ID of the app
            key_id: ID of the API key
            
        Returns:
            Status message or None if not found
        """
        api_key = self.api_key_repository.get_by_id_and_app(db, key_id, app_id)
        
        if not api_key:
            return None
        
        # Toggle the active status
        api_key.is_active = not api_key.is_active
        
        # Save changes
        self.api_key_repository.update(db, api_key)
        
        status_text = "activated" if api_key.is_active else "deactivated"
        logger.info(f"API key {key_id} {status_text} for app {app_id}")
        return f"API key {status_text} successfully" 