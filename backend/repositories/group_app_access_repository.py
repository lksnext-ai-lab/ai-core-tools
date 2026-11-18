"""Persistence operations for explicit group-to-app access policies."""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from models.external_group import ExternalGroup
from models.group_app_access_rule import GroupAppAccessRole, GroupAppAccessRule
from models.app import App
from models.provisioning_connection import ProvisioningConnection
from models.user_external_identity import UserExternalIdentity


class GroupAppAccessRepository:
    """Repository for connection-scoped group access rules."""

    @staticmethod
    def get_rule_for_connection(
        db: Session, app_id: int, rule_id: int, connection_id: int
    ) -> Optional[GroupAppAccessRule]:
        """Return an app rule only if its group belongs to the given connection."""
        return db.execute(
            select(GroupAppAccessRule)
            .join(GroupAppAccessRule.group)
            .join(
                ProvisioningConnection,
                ProvisioningConnection.id == ExternalGroup.connection_id,
            )
            .options(joinedload(GroupAppAccessRule.group))
            .where(
                GroupAppAccessRule.id == rule_id,
                GroupAppAccessRule.app_id == app_id,
                ExternalGroup.connection_id == connection_id,
                ProvisioningConnection.is_active.is_(True),
            )
        ).scalar_one_or_none()

    @staticmethod
    def get_by_group_and_app(
        db: Session, app_id: int, group_id: int, connection_id: int
    ) -> Optional[GroupAppAccessRule]:
        """Return a group/app audit row only within the given connection."""
        return db.execute(
            select(GroupAppAccessRule)
            .join(GroupAppAccessRule.group)
            .join(
                ProvisioningConnection,
                ProvisioningConnection.id == ExternalGroup.connection_id,
            )
            .options(joinedload(GroupAppAccessRule.group))
            .where(
                GroupAppAccessRule.app_id == app_id,
                GroupAppAccessRule.group_id == group_id,
                ExternalGroup.connection_id == connection_id,
                ProvisioningConnection.is_active.is_(True),
            )
        ).scalar_one_or_none()

    @staticmethod
    def list_for_connection(
        db: Session, app_id: int, connection_id: int, offset: int = 0, limit: int = 100
    ) -> list[GroupAppAccessRule]:
        """List rules for one app and one external connection only."""
        return list(
            db.execute(
                select(GroupAppAccessRule)
                .join(GroupAppAccessRule.group)
                .join(
                    ProvisioningConnection,
                    ProvisioningConnection.id == ExternalGroup.connection_id,
                )
                .options(joinedload(GroupAppAccessRule.group))
                .where(
                    GroupAppAccessRule.app_id == app_id,
                    ExternalGroup.connection_id == connection_id,
                    ProvisioningConnection.is_active.is_(True),
                )
                .order_by(GroupAppAccessRule.id)
                .offset(offset)
                .limit(limit)
            ).scalars().unique().all()
        )

    @staticmethod
    def list_eligible_groups(
        db: Session,
        app_id: int,
        connection_id: int,
        offset: int,
        limit: int,
    ) -> tuple[list[ExternalGroup], int]:
        """Return active groups in the manager's connection for one app."""
        conditions = (
            ExternalGroup.connection_id == connection_id,
            ExternalGroup.is_active.is_(True),
        )
        total = db.execute(
            select(func.count(ExternalGroup.id))
            .select_from(ExternalGroup)
            .join(App, App.app_id == app_id)
            .join(
                ProvisioningConnection,
                ProvisioningConnection.id == ExternalGroup.connection_id,
            )
            .where(*conditions, ProvisioningConnection.is_active.is_(True))
        ).scalar_one()
        groups = list(
            db.execute(
                select(ExternalGroup)
                .join(App, App.app_id == app_id)
                .join(
                    ProvisioningConnection,
                    ProvisioningConnection.id == ExternalGroup.connection_id,
                )
                .where(*conditions, ProvisioningConnection.is_active.is_(True))
                .order_by(ExternalGroup.id)
                .offset(offset)
                .limit(limit)
            ).scalars().all()
        )
        return groups, total

    @staticmethod
    def get_group(
        db: Session, app_id: int, group_id: int, connection_id: int
    ) -> Optional[ExternalGroup]:
        """Return an active group for the app only when it belongs to the connection."""
        return db.execute(
            select(ExternalGroup)
            .join(App, App.app_id == app_id)
            .join(
                ProvisioningConnection,
                ProvisioningConnection.id == ExternalGroup.connection_id,
            )
            .where(
                ExternalGroup.id == group_id,
                ExternalGroup.connection_id == connection_id,
                ExternalGroup.is_active.is_(True),
                ProvisioningConnection.is_active.is_(True),
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
        connection_id: int,
        role: GroupAppAccessRole,
        created_by_user_id: int,
    ) -> GroupAppAccessRule:
        """Create or update a rule, recovering from concurrent first-time inserts."""
        rule = GroupAppAccessRepository.get_by_group_and_app(
            db, app_id, group_id, connection_id
        )
        if rule is None:
            try:
                with db.begin_nested():
                    rule = GroupAppAccessRule(
                        app_id=app_id,
                        group_id=group_id,
                        role=role,
                        created_by_user_id=created_by_user_id,
                        is_active=True,
                    )
                    db.add(rule)
                    db.flush()
            except IntegrityError as exc:
                if not GroupAppAccessRepository._is_group_app_unique_conflict(exc):
                    raise
                rule = GroupAppAccessRepository.get_by_group_and_app(
                    db, app_id, group_id, connection_id
                )
                if rule is None:
                    raise
                rule.role = role
                rule.is_active = True
                rule.created_by_user_id = created_by_user_id
        else:
            rule.role = role
            rule.is_active = True
            rule.created_by_user_id = created_by_user_id
        db.commit()
        db.refresh(rule)
        return rule

    @staticmethod
    def _is_group_app_unique_conflict(exc: IntegrityError) -> bool:
        """Recognize only the unique constraint protecting one group/app rule."""
        constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint_name == "uq_group_app_access_rule_group_app":
            return True
        message = str(exc.orig)
        return (
            "UNIQUE constraint failed: group_app_access_rule.group_id, "
            "group_app_access_rule.app_id"
        ) in message

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
