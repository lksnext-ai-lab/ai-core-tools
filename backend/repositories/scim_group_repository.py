"""Persistence operations for connection-scoped SCIM groups."""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from models.external_group import ExternalGroup
from models.external_group_membership import ExternalGroupMembership
from models.user_external_identity import UserExternalIdentity


class SCIMGroupRepository:
    """Repository for external groups and their direct memberships."""

    @staticmethod
    def get_by_scim_id(
        db: Session, connection_id: int, scim_id: str
    ) -> Optional[ExternalGroup]:
        """Find an active group by its connection-scoped SCIM identifier."""
        return db.execute(
            select(ExternalGroup)
            .options(
                selectinload(ExternalGroup.memberships)
                .joinedload(ExternalGroupMembership.user_external_identity)
                .joinedload(UserExternalIdentity.user)
            )
            .where(
                ExternalGroup.connection_id == connection_id,
                ExternalGroup.scim_id == scim_id,
                ExternalGroup.is_active.is_(True),
            )
        ).scalar_one_or_none()

    @staticmethod
    def get_by_external_id(
        db: Session, connection_id: int, external_id: str
    ) -> Optional[ExternalGroup]:
        """Find a group by its source identifier, including inactive rows."""
        return db.execute(
            select(ExternalGroup).where(
                ExternalGroup.connection_id == connection_id,
                ExternalGroup.external_id == external_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def find(
        db: Session,
        connection_id: int,
        start_index: int,
        count: int,
        external_id: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> tuple[list[ExternalGroup], int]:
        """Return a paginated, connection-scoped active group query."""
        conditions = [
            ExternalGroup.connection_id == connection_id,
            ExternalGroup.is_active.is_(True),
        ]
        if external_id is not None:
            conditions.append(ExternalGroup.external_id == external_id)
        if display_name is not None:
            conditions.append(func.lower(ExternalGroup.display_name) == display_name.lower())
        base = select(ExternalGroup).where(*conditions)
        total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
        rows = db.execute(
            base.options(
                selectinload(ExternalGroup.memberships)
                .joinedload(ExternalGroupMembership.user_external_identity)
                .joinedload(UserExternalIdentity.user)
            )
            .order_by(ExternalGroup.id)
            .offset(start_index - 1)
            .limit(count)
        ).scalars().unique().all()
        return rows, total

    @staticmethod
    def get_membership(
        db: Session, group_id: int, identity_id: int
    ) -> Optional[ExternalGroupMembership]:
        """Find one direct membership."""
        return db.execute(
            select(ExternalGroupMembership).where(
                ExternalGroupMembership.group_id == group_id,
                ExternalGroupMembership.user_external_identity_id == identity_id,
            )
        ).scalar_one_or_none()
