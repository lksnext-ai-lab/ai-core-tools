"""Persistence operations for explicit group-to-app access policies."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from models.external_group import ExternalGroup
from models.external_group_membership import ExternalGroupMembership
from models.group_app_access_rule import GroupAppAccessRole, GroupAppAccessRule
from models.provisioning_connection import ProvisioningConnection
from models.user_external_identity import UserExternalIdentity


class GroupAppAccessRepository:
    """Repository for connection-scoped group access rules."""

    @staticmethod
    def get_rule(db: Session, app_id: int, rule_id: int) -> Optional[GroupAppAccessRule]:
        """Return one rule belonging to the requested app."""
        return db.execute(
            select(GroupAppAccessRule)
            .options(joinedload(GroupAppAccessRule.group))
            .where(GroupAppAccessRule.id == rule_id, GroupAppAccessRule.app_id == app_id)
        ).scalar_one_or_none()

    @staticmethod
    def get_by_group_and_app(
        db: Session, app_id: int, group_id: int
    ) -> Optional[GroupAppAccessRule]:
        """Return the audit row for a group/app pair, including inactive rows."""
        return db.execute(
            select(GroupAppAccessRule)
            .options(joinedload(GroupAppAccessRule.group))
            .where(
                GroupAppAccessRule.app_id == app_id,
                GroupAppAccessRule.group_id == group_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def list_for_connection(
        db: Session, app_id: int, connection_id: int
    ) -> list[GroupAppAccessRule]:
        """List rules for one app and one external connection only."""
        return list(
            db.execute(
                select(GroupAppAccessRule)
                .join(GroupAppAccessRule.group)
                .options(joinedload(GroupAppAccessRule.group))
                .where(
                    GroupAppAccessRule.app_id == app_id,
                    ExternalGroup.connection_id == connection_id,
                )
                .order_by(GroupAppAccessRule.id)
            ).scalars().unique().all()
        )

    @staticmethod
    def get_group(
        db: Session, group_id: int, connection_id: int
    ) -> Optional[ExternalGroup]:
        """Return an active group only when it belongs to the connection."""
        return db.execute(
            select(ExternalGroup).where(
                ExternalGroup.id == group_id,
                ExternalGroup.connection_id == connection_id,
                ExternalGroup.is_active.is_(True),
            )
        ).scalar_one_or_none()

    @staticmethod
    def get_identity(
        db: Session, user_id: int, connection_id: Optional[int] = None
    ) -> Optional[UserExternalIdentity]:
        """Return the caller's active external identity, optionally scoped."""
        conditions = [
            UserExternalIdentity.user_id == user_id,
            UserExternalIdentity.is_active.is_(True),
        ]
        if connection_id is not None:
            conditions.append(UserExternalIdentity.connection_id == connection_id)
        return db.execute(
            select(UserExternalIdentity)
            .join(
                ProvisioningConnection,
                ProvisioningConnection.id == UserExternalIdentity.connection_id,
            )
            .where(*conditions, ProvisioningConnection.is_active.is_(True))
        ).scalar_one_or_none()

    @staticmethod
    def upsert_rule(
        db: Session,
        app_id: int,
        group_id: int,
        role: GroupAppAccessRole,
        created_by_user_id: int,
    ) -> GroupAppAccessRule:
        """Create a rule or update/reactivate its existing audit row."""
        rule = GroupAppAccessRepository.get_by_group_and_app(db, app_id, group_id)
        if rule is None:
            rule = GroupAppAccessRule(
                app_id=app_id,
                group_id=group_id,
                role=role,
                created_by_user_id=created_by_user_id,
                is_active=True,
            )
            db.add(rule)
        else:
            rule.role = role
            rule.is_active = True
            rule.created_by_user_id = created_by_user_id
        db.commit()
        db.refresh(rule)
        return rule

    @staticmethod
    def update_rule(
        db: Session, rule: GroupAppAccessRule, role: Optional[GroupAppAccessRole],
        is_active: Optional[bool],
    ) -> GroupAppAccessRule:
        """Update a policy while retaining its row."""
        if role is not None:
            rule.role = role
        if is_active is not None:
            rule.is_active = is_active
        db.commit()
        db.refresh(rule)
        return rule

    @staticmethod
    def get_effective_role(
        db: Session, user_id: int, app_id: int
    ) -> Optional[GroupAppAccessRole]:
        """Return the highest active group-derived role for a user and app."""
        rows = db.execute(
            select(GroupAppAccessRule.role)
            .join(ExternalGroup, GroupAppAccessRule.group_id == ExternalGroup.id)
            .join(
                ExternalGroupMembership,
                ExternalGroupMembership.group_id == ExternalGroup.id,
            )
            .join(
                UserExternalIdentity,
                UserExternalIdentity.id
                == ExternalGroupMembership.user_external_identity_id,
            )
            .join(
                ProvisioningConnection,
                ProvisioningConnection.id == ExternalGroup.connection_id,
            )
            .where(
                GroupAppAccessRule.app_id == app_id,
                GroupAppAccessRule.is_active.is_(True),
                ExternalGroup.is_active.is_(True),
                UserExternalIdentity.user_id == user_id,
                UserExternalIdentity.is_active.is_(True),
                ExternalGroup.connection_id == UserExternalIdentity.connection_id,
                ProvisioningConnection.is_active.is_(True),
            )
        ).scalars().all()
        if not rows:
            return None
        return max(rows, key=lambda value: 1 if value == GroupAppAccessRole.EDITOR else 0)
