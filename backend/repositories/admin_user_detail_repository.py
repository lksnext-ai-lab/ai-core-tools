"""ORM queries for the internal admin user detail view."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.api_key import APIKey
from models.app import App
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from models.user import User


@dataclass
class OwnedAppDetailRecord:
    """Whitelisted owned-app metadata for a user detail response."""

    app_id: int
    name: Optional[str]
    is_frozen: bool


@dataclass
class CollaborationDetailRecord:
    """Whitelisted collaboration and associated app metadata."""

    app_id: int
    app_name: Optional[str]
    role: CollaborationRole
    status: CollaborationStatus
    invited_at: datetime
    accepted_at: Optional[datetime]
    is_frozen: bool


@dataclass
class APIKeyDetailRecord:
    """Whitelisted API-key metadata; credential material is never selected."""

    key_id: int
    name: str
    app_id: int
    app_name: Optional[str]
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]


class AdminUserDetailRepository:
    """Fetch a user's detail records without loading unrelated relationships."""

    def __init__(self, db: Session):
        self.db = db

    def get_user(self, user_id: int) -> Optional[User]:
        """Return a user by ID, or ``None`` if it does not exist."""
        return self.db.execute(
            select(User).where(User.user_id == user_id)
        ).scalar_one_or_none()

    def get_owned_apps(self, user_id: int) -> List[OwnedAppDetailRecord]:
        """Return apps owned by the requested user."""
        rows = self.db.execute(
            select(App.app_id, App.name, App.is_frozen)
            .where(App.owner_id == user_id)
            .order_by(App.app_id)
        ).all()
        return [OwnedAppDetailRecord(*row) for row in rows]

    def get_collaborations(self, user_id: int) -> List[CollaborationDetailRecord]:
        """Return the requested user's collaboration rows and their app metadata."""
        rows = self.db.execute(
            select(
                AppCollaborator.app_id,
                App.name,
                AppCollaborator.role,
                AppCollaborator.status,
                AppCollaborator.invited_at,
                AppCollaborator.accepted_at,
                AppCollaborator.is_frozen,
            )
            .join(App, App.app_id == AppCollaborator.app_id)
            .where(AppCollaborator.user_id == user_id)
            .order_by(AppCollaborator.app_id)
        ).all()
        return [CollaborationDetailRecord(*row) for row in rows]

    def get_api_keys(self, user_id: int) -> List[APIKeyDetailRecord]:
        """Return the requested user's API key rows and their app metadata."""
        rows = self.db.execute(
            select(
                APIKey.key_id,
                APIKey.name,
                APIKey.app_id,
                App.name,
                APIKey.is_active,
                APIKey.created_at,
                APIKey.last_used_at,
            )
            .join(App, App.app_id == APIKey.app_id)
            .where(APIKey.user_id == user_id)
            .order_by(APIKey.key_id)
        ).all()
        return [APIKeyDetailRecord(*row) for row in rows]
