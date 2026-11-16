"""Business logic for explicit external-group app access policies."""

from typing import Optional

from sqlalchemy.orm import Session

from models.group_app_access_rule import GroupAppAccessRole, GroupAppAccessRule
from repositories.app_collaboration_repository import AppCollaborationRepository
from repositories.group_app_access_repository import GroupAppAccessRepository
from schemas.group_app_access_schemas import GroupAppAccessRuleListItem


class GroupAppAccessNotFoundError(ValueError):
    """Raised when a requested policy or eligible group is not available."""


class GroupAppAccessForbiddenError(PermissionError):
    """Raised when the caller has no linked identity for the group connection."""


class GroupAppAccessService:
    """Manage provider-neutral, connection-scoped group access rules."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = GroupAppAccessRepository()

    def _authorize_manager(self, app_id: int, user_id: int) -> None:
        if not AppCollaborationRepository(self.db).can_user_administer_app(user_id, app_id):
            raise GroupAppAccessForbiddenError("Only an app owner or administrator may manage rules")

    def _caller_connection(self, app_id: int, user_id: int) -> int:
        self._authorize_manager(app_id, user_id)
        identity = self.repository.get_identity(self.db, user_id)
        if identity is None:
            raise GroupAppAccessForbiddenError("Caller has no active provisioning identity")
        return identity.connection_id

    @staticmethod
    def _to_response(rule: GroupAppAccessRule) -> GroupAppAccessRuleListItem:
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

    def list_rules(self, app_id: int, user_id: int) -> list[GroupAppAccessRuleListItem]:
        """List all audit rows visible to the caller's external connection."""
        connection_id = self._caller_connection(app_id, user_id)
        rules = self.repository.list_for_connection(self.db, app_id, connection_id)
        return [self._to_response(rule) for rule in rules]

    def create_rule(
        self, app_id: int, user_id: int, group_id: int, role: GroupAppAccessRole
    ) -> GroupAppAccessRuleListItem:
        """Create or reactivate a valid group policy."""
        connection_id = self._caller_connection(app_id, user_id)
        if self.repository.get_group(self.db, group_id, connection_id) is None:
            raise GroupAppAccessNotFoundError("Active group is not in the caller's connection")
        return self._to_response(
            self.repository.upsert_rule(self.db, app_id, group_id, role, user_id)
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
        rule = self.repository.get_rule(self.db, app_id, rule_id)
        if rule is None or rule.group.connection_id != connection_id:
            raise GroupAppAccessNotFoundError("Group access rule not found")
        if self.repository.get_group(self.db, rule.group_id, connection_id) is None and is_active:
            raise GroupAppAccessNotFoundError("Group is no longer active")
        return self._to_response(
            self.repository.update_rule(self.db, rule, role, is_active)
        )

    def delete_rule(self, app_id: int, rule_id: int, user_id: int) -> GroupAppAccessRuleListItem:
        """Disable a policy while preserving its audit history."""
        return self.update_rule(app_id, rule_id, user_id, None, False)

    def effective_group_role(self, user_id: int, app_id: int) -> Optional[GroupAppAccessRole]:
        """Compute the highest role granted by active group memberships."""
        return self.repository.get_effective_role(self.db, user_id, app_id)
