from typing import List, Optional
from sqlalchemy.orm import Session
from models.api_key import APIKey
from models.app import App
from utils.logger import get_logger
from datetime import datetime
from sqlalchemy.orm import joinedload

logger = get_logger(__name__)


class APIKeyRepository:
    """Repository class for API key database operations"""
    
    @staticmethod
    def get_by_app_id(db: Session, app_id: int) -> List[APIKey]:
        """
        Get all API keys for a specific app
        
        Args:
            db: Database session
            app_id: ID of the app
            
        Returns:
            List of API keys
        """
        return db.query(APIKey).filter(APIKey.app_id == app_id).all()

    @staticmethod
    def get_active_by_app_and_key(db: Session, app_id: int, api_key: str) -> Optional[APIKey]:
        """
        Get an active API key by app and key value, including app owner relationship.

        Args:
            db: Database session
            app_id: ID of the app
            api_key: API key value

        Returns:
            API key or None if not found/active
        """
        return (
            db.query(APIKey)
            .options(joinedload(APIKey.app).joinedload(App.owner))
            .filter(
                APIKey.app_id == app_id,
                APIKey.key == api_key,
                APIKey.is_active.is_(True)
            )
            .first()
        )
    
    @staticmethod
    def get_by_id_and_app(db: Session, key_id: int, app_id: int) -> Optional[APIKey]:
        """
        Get an API key by its ID and app ID
        
        Args:
            db: Database session
            key_id: ID of the API key
            app_id: ID of the app
            
        Returns:
            API key or None if not found
        """
        return db.query(APIKey).filter(
            APIKey.key_id == key_id,
            APIKey.app_id == app_id
        ).first()
    
    @staticmethod
    def create(db: Session, api_key: APIKey) -> APIKey:
        """
        Create a new API key
        
        Args:
            db: Database session
            api_key: API key instance to create
            
        Returns:
            Created API key
        """
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        return api_key
    
    @staticmethod
    def update(db: Session, api_key: APIKey) -> APIKey:
        """
        Update an existing API key
        
        Args:
            db: Database session
            api_key: API key instance to update
            
        Returns:
            Updated API key
        """
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        return api_key

    @staticmethod
    def update_last_used_at(db: Session, api_key: APIKey, last_used_at: datetime) -> APIKey:
        """
        Update last used timestamp for an API key.

        Args:
            db: Database session
            api_key: API key instance to update
            last_used_at: Timestamp to set

        Returns:
            Updated API key
        """
        api_key.last_used_at = last_used_at
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        return api_key
    
    @staticmethod
    def delete(db: Session, api_key: APIKey) -> None:
        """
        Delete an API key
        
        Args:
            db: Database session
            api_key: API key instance to delete
        """
        db.delete(api_key)
        db.commit()
    
    @staticmethod
    def delete_by_app_id(db: Session, app_id: int) -> int:
        """
        Delete all API keys for a specific app
        
        Args:
            db: Database session
            app_id: ID of the app
            
        Returns:
            Number of deleted API keys
        """
        deleted_count = db.query(APIKey).filter(APIKey.app_id == app_id).delete()
        db.commit()
        return deleted_count
