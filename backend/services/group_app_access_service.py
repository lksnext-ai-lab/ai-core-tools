"""Business logic for explicit external-group app access policies."""

from typing import Optional

from sqlalchemy.orm import Session

from models.group_app_access_rule import GroupAppAccessRole, GroupAppAccessRule
from repositories.app_collaboration_repository import AppCollaborationRepository
from repositories.app_role_repository import AppRoleRepository
from repositories.group_app_access_repository import GroupAppAccessRepository
from schemas.group_app_access_schemas import (
    EligibleGroupListItem,
    EligibleGroupsPage,
    GroupAppAccessRuleListItem,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class GroupAppAccessNotFoundError(ValueError):
    """Raised when a requested policy or eligible group is not available."""


class GroupAppAccessForbiddenError(PermissionError):
    """Raised when the caller cannot manage the requested app policies."""


class GroupAppAccessInvalidRoleError(ValueError):
    """Raised when a policy attempts to grant a role outside VIEWER/EDITOR."""


class GroupAppAccessService:
    """Manage provider-neutral, connection-scoped group access rules."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = GroupAppAccessRepository()

    def authorize_manager(self, app_id: int, user_id: int) -> None:
        """Require app ownership or an accepted app-administrator collaboration."""
        if not AppCollaborationRepository(self.db).can_user_administer_app(user_id, app_id):
            logger.warning(
                "Denied group policy access actor_user_id=%s app_id=%s",
                user_id,
                app_id,
            )
            raise GroupAppAccessForbiddenError(
                "Only an app owner or administrator may manage group policies."
            )

    def _caller_connection(self, app_id: int, user_id: int) -> Optional[int]:
        """Return the caller's active linked connection after app authorization."""
        self.authorize_manager(app_id, user_id)
        identity = self.repository.get_identity(self.db, user_id)
        return identity.connection_id if identity is not None else None

    @staticmethod
    def _validate_role(role: GroupAppAccessRole) -> GroupAppAccessRole:
        """Normalize and restrict policy roles to VIEWER or EDITOR."""
        try:
            return GroupAppAccessRole(role)
        except (TypeError, ValueError) as exc:
            raise GroupAppAccessInvalidRoleError(
                "Only VIEWER and EDITOR group roles are supported."
            ) from exc

    @staticmethod
    def _to_response(rule: GroupAppAccessRule) -> GroupAppAccessRuleListItem:
        """Convert a persisted rule to its typed API response."""
        return GroupAppAccessRuleListItem(
            id=rule.id,
            group_id=rule.group_id,
            app_id=rule.app_id,
            role=rule.role,
            created_by_user_id=rule.created_by_user_id,
            is_active=rule.is_active,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
            group_display_name=rule.group.display_name,
            connection_id=rule.group.connection_id,
        )

    def list_rules(
        self, app_id: int, user_id: int, offset: int = 0, limit: int = 100
    ) -> list[GroupAppAccessRuleListItem]:
        """List app policy audit rows only from the caller's active connection."""
        connection_id = self._caller_connection(app_id, user_id)
        if connection_id is None:
            return []
        rules = self.repository.list_for_connection(
            self.db, app_id, connection_id, offset, limit
        )
        return [self._to_response(rule) for rule in rules]

    def list_eligible_groups(
        self, app_id: int, user_id: int, offset: int, limit: int
    ) -> EligibleGroupsPage:
        """List active group choices from the manager's linked connection."""
        connection_id = self._caller_connection(app_id, user_id)
        if connection_id is None:
            return EligibleGroupsPage(items=[], total=0, offset=offset, limit=limit)
        groups, total = self.repository.list_eligible_groups(
            self.db, app_id, connection_id, offset, limit
        )
        return EligibleGroupsPage(
            items=[
                EligibleGroupListItem(group_id=group.id, display_name=group.display_name)
                for group in groups
            ],
            total=total,
            offset=offset,
            limit=limit,
        )

    def create_rule(
        self, app_id: int, user_id: int, group_id: int, role: GroupAppAccessRole
    ) -> GroupAppAccessRuleListItem:
        """Create or reactivate a valid group policy."""
        connection_id = self._caller_connection(app_id, user_id)
        if connection_id is None:
            raise GroupAppAccessForbiddenError(
                "An active linked provisioning identity is required."
            )
        role = self._validate_role(role)
        if self.repository.get_group(
            self.db, app_id, group_id, connection_id
        ) is None:
            logger.warning(
                "Rejected group policy choice actor_user_id=%s app_id=%s group_id=%s",
                user_id,
                app_id,
                group_id,
            )
            raise GroupAppAccessNotFoundError("Active group not found.")
        logger.info(
            "Created or reactivated group policy actor_user_id=%s app_id=%s group_id=%s",
            user_id,
            app_id,
            group_id,
        )
        return self._to_response(
            self.repository.upsert_rule(
                self.db, app_id, group_id, connection_id, role, user_id
            )
        )

    def update_rule(
        self,
        app_id: int,
        rule_id: int,
        user_id: int,
        role: Optional[GroupAppAccessRole],
        is_active: Optional[bool],
    ) -> GroupAppAccessRuleListItem:
        """Update or disable a policy without deleting its audit row."""
        connection_id = self._caller_connection(app_id, user_id)
        if connection_id is None:
            raise GroupAppAccessForbiddenError(
                "An active linked provisioning identity is required."
            )
        if role is not None:
            role = self._validate_role(role)
        rule = self.repository.get_rule_for_connection(
            self.db, app_id, rule_id, connection_id
        )
        if rule is None:
            raise GroupAppAccessNotFoundError("Group access rule not found.")
        if (role is not None or is_active is True) and self.repository.get_group(
            self.db, app_id, rule.group_id, connection_id
        ) is None:
            raise GroupAppAccessNotFoundError("Active group not found.")
        logger.info(
            "Updated group policy actor_user_id=%s app_id=%s rule_id=%s active=%s",
            user_id,
            app_id,
            rule_id,
            is_active,
        )
        return self._to_response(
            self.repository.update_rule(self.db, rule, role, is_active)
        )

    def delete_rule(
        self, app_id: int, rule_id: int, user_id: int
    ) -> GroupAppAccessRuleListItem:
        """Disable a policy while preserving its audit history."""
        return self.update_rule(app_id, rule_id, user_id, None, False)

    def effective_group_role(
        self, user_id: int, app_id: int
    ) -> Optional[GroupAppAccessRole]:
        """Return group-derived access for the existing authorization integration."""
        return self.effective_group_roles(user_id, [app_id]).get(app_id)

    def effective_group_roles(
        self, user_id: int, app_ids: Optional[list[int]] = None
    ) -> dict[int, GroupAppAccessRole]:
        """Return current group-derived access for one user across scoped apps."""
        return AppRoleRepository(self.db).get_effective_group_roles(user_id, app_ids)
