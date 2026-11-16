"""Persistence operations for connection-scoped SCIM users."""

from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from models.user import User
from models.user_external_identity import UserExternalIdentity
from models.oidc_identity_link import OIDCIdentityLink


class SCIMUserRepository:
    """Repository for UserExternalIdentity rows and their local users."""

    @staticmethod
    def get_by_scim_id(
        db: Session, connection_id: int, scim_id: str
    ) -> Optional[UserExternalIdentity]:
        """Find a resource by its connection-scoped SCIM identifier."""
        return db.execute(
            select(UserExternalIdentity)
            .options(joinedload(UserExternalIdentity.user))
            .where(
                UserExternalIdentity.connection_id == connection_id,
                UserExternalIdentity.scim_id == scim_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def get_by_external_id(
        db: Session, connection_id: int, external_id: str
    ) -> Optional[UserExternalIdentity]:
        """Find a resource by its connection-scoped source identifier."""
        return db.execute(
            select(UserExternalIdentity)
            .options(joinedload(UserExternalIdentity.user))
            .where(
                UserExternalIdentity.connection_id == connection_id,
                UserExternalIdentity.external_id == external_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def find(
        db: Session,
        connection_id: int,
        start_index: int,
        count: int,
        external_id: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> tuple[list[UserExternalIdentity], int]:
        """Return a paginated, connection-scoped resource query."""
        conditions = [UserExternalIdentity.connection_id == connection_id]
        if external_id is not None:
            conditions.append(UserExternalIdentity.external_id == external_id)
        if user_name is not None:
            conditions.append(
                func.lower(UserExternalIdentity.user_name) == user_name.lower()
            )
        base = select(UserExternalIdentity).where(*conditions)
        total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
        rows = db.execute(
            base.options(joinedload(UserExternalIdentity.user))
            .order_by(UserExternalIdentity.id)
            .offset(start_index - 1)
            .limit(count)
        ).scalars().unique().all()
        return rows, total

    @staticmethod
    def get_email_users(db: Session, email: str) -> list[User]:
        """Return all local accounts matching an email, case-insensitively."""
        return db.execute(
            select(User).where(func.lower(User.email) == email.lower())
        ).scalars().all()

    @staticmethod
    def get_external_identities_for_user(
        db: Session, user_id: int
    ) -> list[UserExternalIdentity]:
        """Return every external identity currently attached to a local user."""
        return db.execute(
            select(UserExternalIdentity)
            .options(joinedload(UserExternalIdentity.connection))
            .where(UserExternalIdentity.user_id == user_id)
        ).scalars().unique().all()

    @staticmethod
    def get_oidc_linked_user(
        db: Session, connection_id: int, external_id: str
    ) -> Optional[User]:
        """Return the user selected by an explicit SCIM identity mapping."""
        statement = (
            select(User)
            .join(OIDCIdentityLink, OIDCIdentityLink.user_id == User.user_id)
            .where(
                OIDCIdentityLink.connection_id == connection_id,
                OIDCIdentityLink.external_id == external_id,
            )
        )
        return db.execute(statement).scalar_one_or_none()
