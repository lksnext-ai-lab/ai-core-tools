"""Persistence queries for current app-role sources."""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import and_, case, func, select, union
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql.selectable import CTE

from models.app import App
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from models.external_group import ExternalGroup
from models.external_group_membership import ExternalGroupMembership
from models.group_app_access_rule import GroupAppAccessRole, GroupAppAccessRule
from models.provisioning_connection import ProvisioningConnection
from models.user_external_identity import UserExternalIdentity


@dataclass(frozen=True)
class AppRoleSource:
    """Current app access-source data returned by a role repository query."""

    app: App
    collaboration_role: Optional[CollaborationRole]
    group_role: Optional[GroupAppAccessRole]


class AppRoleRepository:
    """Read ownership, collaboration, and active group-role sources."""

    def __init__(self, db: Session) -> None:
        """Bind role-source reads to the request database session."""
        self.db = db

    def get_app_role_sources(
        self, user_id: int, app_ids: list[int]
    ) -> list[AppRoleSource]:
        """Return all current role sources for scoped apps in one query."""
        if not user_id or user_id <= 0 or not app_ids:
            return []

        group_roles = self._effective_group_role_cte(user_id, app_ids)
        statement = (
            select(App, AppCollaborator.role, group_roles.c.role_rank)
            .outerjoin(
                AppCollaborator,
                and_(
                    AppCollaborator.app_id == App.app_id,
                    AppCollaborator.user_id == user_id,
                    AppCollaborator.status == CollaborationStatus.ACCEPTED,
                ),
            )
            .outerjoin(group_roles, group_roles.c.app_id == App.app_id)
            .options(joinedload(App.owner))
            .where(App.app_id.in_(app_ids))
        )
        rows = self.db.execute(statement).unique().all()
        return [
            AppRoleSource(
                app=row[0],
                collaboration_role=row[1],
                group_role=(
                    GroupAppAccessRole.EDITOR
                    if row[2] == 1
                    else GroupAppAccessRole.VIEWER
                    if row[2] is not None
                    else None
                ),
            )
            for row in rows
        ]

    def get_accessible_app_role_sources(
        self, user_id: int, limit: Optional[int] = None, offset: int = 0
    ) -> tuple[list[AppRoleSource], bool]:
        """Return an ordered page of current app candidates and their role sources."""
        if not user_id or user_id <= 0:
            return [], False

        group_roles = self._effective_group_role_cte(user_id)
        collaborations = self._accepted_collaboration_cte(user_id)
        candidate_app_ids = union(
            select(App.app_id.label("app_id")).where(App.owner_id == user_id),
            select(collaborations.c.app_id.label("app_id")).where(
                collaborations.c.row_number == 1,
                collaborations.c.role != CollaborationRole.USER,
            ),
            select(group_roles.c.app_id.label("app_id")),
        ).subquery("accessible_app_ids")

        statement = (
            select(App, collaborations.c.role, group_roles.c.role_rank)
            .outerjoin(
                collaborations,
                and_(
                    collaborations.c.app_id == App.app_id,
                    collaborations.c.row_number == 1,
                ),
            )
            .outerjoin(group_roles, group_roles.c.app_id == App.app_id)
            .join(candidate_app_ids, candidate_app_ids.c.app_id == App.app_id)
            .options(joinedload(App.owner))
            .order_by(App.create_date.desc().nullslast(), App.app_id.desc())
            .offset(offset)
        )
        if limit is not None:
            statement = statement.limit(limit + 1)

        rows = self.db.execute(statement).unique().all()
        has_more = limit is not None and len(rows) > limit
        if has_more:
            rows = rows[:limit]
        sources = [
            AppRoleSource(
                app=row[0],
                collaboration_role=row[1],
                group_role=(
                    GroupAppAccessRole.EDITOR
                    if row[2] == 1
                    else GroupAppAccessRole.VIEWER
                    if row[2] is not None
                    else None
                ),
            )
            for row in rows
        ]
        return sources, has_more

    def get_effective_group_roles(
        self, user_id: int, app_ids: Optional[list[int]] = None
    ) -> dict[int, GroupAppAccessRole]:
        """Return active group-derived roles scoped to a user and optional apps."""
        if app_ids is not None and not app_ids:
            return {}

        group_roles = self._effective_group_role_cte(user_id, app_ids)
        statement = select(group_roles.c.app_id, group_roles.c.role_rank)
        rows = self.db.execute(statement).all()
        return {
            app_id: (
                GroupAppAccessRole.EDITOR
                if role_rank == 1
                else GroupAppAccessRole.VIEWER
            )
            for app_id, role_rank in rows
        }

    @staticmethod
    def _effective_group_role_cte(
        user_id: int, app_ids: Optional[list[int]] = None
    ) -> CTE:
        """Build the active, user-scoped group-role aggregate."""
        statement = (
            select(
                GroupAppAccessRule.app_id,
                func.max(
                    case(
                        (GroupAppAccessRule.role == GroupAppAccessRole.EDITOR, 1),
                        else_=0,
                    )
                ).label("role_rank"),
            )
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
                GroupAppAccessRule.is_active.is_(True),
                ExternalGroup.is_active.is_(True),
                UserExternalIdentity.user_id == user_id,
                UserExternalIdentity.is_active.is_(True),
                ExternalGroup.connection_id == UserExternalIdentity.connection_id,
                ProvisioningConnection.is_active.is_(True),
            )
        )
        if app_ids is not None:
            statement = statement.where(GroupAppAccessRule.app_id.in_(app_ids))
        return statement.group_by(GroupAppAccessRule.app_id).cte(
            "active_group_app_roles"
        )

    @staticmethod
    def _accepted_collaboration_cte(user_id: int) -> CTE:
        """Select one highest accepted manual role per user/app for stable paging."""
        role_rank = case(
            (AppCollaborator.role == CollaborationRole.OWNER, 5),
            (AppCollaborator.role == CollaborationRole.ADMINISTRATOR, 4),
            (AppCollaborator.role == CollaborationRole.EDITOR, 3),
            (AppCollaborator.role == CollaborationRole.VIEWER, 2),
            else_=1,
        )
        return (
            select(
                AppCollaborator.app_id,
                AppCollaborator.role,
                func.row_number()
                .over(
                    partition_by=AppCollaborator.app_id,
                    order_by=role_rank.desc(),
                )
                .label("row_number"),
            )
            .where(
                AppCollaborator.user_id == user_id,
                AppCollaborator.status == CollaborationStatus.ACCEPTED,
            )
            .cte("accepted_app_collaborations")
        )
