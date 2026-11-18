"""Persistence queries for an authenticated user's directly provisioned groups."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from models.app import App
from models.external_group import ExternalGroup
from models.external_group_membership import ExternalGroupMembership
from models.group_app_access_rule import GroupAppAccessRule
from models.provisioning_connection import ProvisioningConnection
from models.user_external_identity import UserExternalIdentity


class MyGroupsRepository:
    """Read-only queries for the authenticated user's eligible SCIM groups."""

    @staticmethod
    def list_groups(
        db: Session, user_id: int, offset: int, limit: int
    ) -> tuple[list[tuple[int, str]], int]:
        """Return active groups with a current direct membership for the user."""
        conditions = MyGroupsRepository._eligible_group_conditions(user_id)
        total = db.execute(
            select(func.count(func.distinct(ExternalGroup.id)))
            .select_from(ExternalGroup)
            .join(ExternalGroupMembership, ExternalGroupMembership.group_id == ExternalGroup.id)
            .join(
                UserExternalIdentity,
                UserExternalIdentity.id
                == ExternalGroupMembership.user_external_identity_id,
            )
            .join(
                ProvisioningConnection,
                ProvisioningConnection.id == UserExternalIdentity.connection_id,
            )
            .where(*conditions)
        ).scalar_one()
        rows = db.execute(
            select(ExternalGroup.id, ExternalGroup.display_name)
            .join(ExternalGroupMembership, ExternalGroupMembership.group_id == ExternalGroup.id)
            .join(
                UserExternalIdentity,
                UserExternalIdentity.id
                == ExternalGroupMembership.user_external_identity_id,
            )
            .join(
                ProvisioningConnection,
                ProvisioningConnection.id == UserExternalIdentity.connection_id,
            )
            .where(*conditions)
            .distinct()
            .order_by(ExternalGroup.id)
            .offset(offset)
            .limit(limit)
        ).all()
        return [(int(group_id), display_name) for group_id, display_name in rows], int(total)

    @staticmethod
    def list_group_apps(
        db: Session, user_id: int, group_id: int, offset: int, limit: int
    ) -> tuple[str, list[tuple[int, str | None, str]], int] | None:
        """Return active app rules for an eligible group, including an empty page."""
        conditions = MyGroupsRepository._eligible_group_conditions(user_id)
        conditions.append(ExternalGroup.id == group_id)
        display_name = db.execute(
            select(ExternalGroup.display_name)
            .select_from(ExternalGroup)
            .join(ExternalGroupMembership, ExternalGroupMembership.group_id == ExternalGroup.id)
            .join(
                UserExternalIdentity,
                UserExternalIdentity.id
                == ExternalGroupMembership.user_external_identity_id,
            )
            .join(
                ProvisioningConnection,
                ProvisioningConnection.id == UserExternalIdentity.connection_id,
            )
            .where(*conditions)
        ).scalar_one_or_none()
        if display_name is None:
            return None

        app_conditions = [
            *conditions,
            GroupAppAccessRule.is_active.is_(True),
            GroupAppAccessRule.app_id == App.app_id,
        ]
        base = (
            select(
                App.app_id,
                App.name,
                GroupAppAccessRule.role,
            )
            .select_from(ExternalGroup)
            .join(ExternalGroupMembership, ExternalGroupMembership.group_id == ExternalGroup.id)
            .join(
                UserExternalIdentity,
                UserExternalIdentity.id
                == ExternalGroupMembership.user_external_identity_id,
            )
            .join(
                ProvisioningConnection,
                ProvisioningConnection.id == UserExternalIdentity.connection_id,
            )
            .join(
                GroupAppAccessRule,
                GroupAppAccessRule.group_id == ExternalGroup.id,
            )
            .join(App, App.app_id == GroupAppAccessRule.app_id)
            .where(*app_conditions)
        )
        base_subquery = base.subquery()
        total = db.execute(
            select(func.count()).select_from(base_subquery)
        ).scalar_one()
        rows = db.execute(
            base.order_by(App.app_id).offset(offset).limit(limit)
        ).all()
        apps = [
            (int(app_id), app_name, role.value)
            for app_id, app_name, role in rows
        ]
        return display_name, apps, int(total)

    @staticmethod
    def _eligible_group_conditions(user_id: int) -> list[ColumnElement[bool]]:
        """Build active identity, direct membership, group, and connection filters."""
        return [
            UserExternalIdentity.user_id == user_id,
            UserExternalIdentity.is_active.is_(True),
            ProvisioningConnection.id == ExternalGroup.connection_id,
            ProvisioningConnection.is_active.is_(True),
            ExternalGroup.is_active.is_(True),
        ]
