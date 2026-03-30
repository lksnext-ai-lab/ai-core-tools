from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.api_key import APIKey
from repositories.api_key_repository import APIKeyRepository


class PublicAuthService:
    """Business logic for public API key authentication."""

    def __init__(self, api_key_repository: APIKeyRepository | None = None):
        self.api_key_repository = api_key_repository or APIKeyRepository()

    def validate_api_key_for_app(self, db: Session, app_id: int, api_key: str) -> APIKey:
        """
        Validate API key for a specific app and update usage metadata.

        Args:
            db: Database session
            app_id: The app ID to validate against
            api_key: The API key value

        Returns:
            The validated API key ORM object

        Raises:
            HTTPException: If authentication fails
        """
        api_key_obj = self.api_key_repository.get_active_by_app_and_key(db, app_id, api_key)

        if not api_key_obj:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or inactive API key for this app",
            )

        app_owner = api_key_obj.app.owner if api_key_obj.app else None
        if app_owner and hasattr(app_owner, "is_active") and not app_owner.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This API key belongs to a deactivated account",
            )

        self.api_key_repository.update_last_used_at(db, api_key_obj, datetime.now())
        return api_key_obj
