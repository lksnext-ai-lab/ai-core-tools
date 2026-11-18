"""Business logic for an authenticated user's read-only SCIM group access view."""

from sqlalchemy.orm import Session

from repositories.my_groups_repository import MyGroupsRepository
from services.app_role_service import AppRoleService
from schemas.my_groups_schemas import (
    GroupContribution,
    MyGroupAppListItem,
    MyGroupAppsPage,
    MyGroupListItem,
    MyGroupsPage,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class MyGroupNotFoundError(LookupError):
    """Raised when a group is not currently eligible for this user."""


class MyGroupsService:
    """Build read-only group and app views from current provisioned records."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = MyGroupsRepository()

    def list_groups(self, user_id: int, offset: int, limit: int) -> MyGroupsPage:
        """List the user's current active direct SCIM group memberships."""
        groups, total = self.repository.list_groups(self.db, user_id, offset, limit)
        logger.info("Listed eligible SCIM groups for user_id=%s count=%s", user_id, total)
        return MyGroupsPage(
            items=[
                MyGroupListItem(group_id=group_id, display_name=display_name)
                for group_id, display_name in groups
            ],
            total=total,
            offset=offset,
            limit=limit,
        )

    def list_group_apps(
        self, user_id: int, group_id: int, offset: int, limit: int
    ) -> MyGroupAppsPage:
        """List active app rules for a currently eligible group."""
        result = self.repository.list_group_apps(
            self.db, user_id, group_id, offset, limit
        )
        if result is None:
            logger.info(
                "Rejected ineligible SCIM group view user_id=%s group_id=%s",
                user_id,
                group_id,
            )
            raise MyGroupNotFoundError("Group not found.")

        display_name, rows, total = result
        effective_roles = AppRoleService(self.db).get_effective_roles(
            user_id,
            [app_id for app_id, _, _ in rows],
        )
        return MyGroupAppsPage(
            group_id=group_id,
            display_name=display_name,
            items=[
                MyGroupAppListItem(
                    app_id=app_id,
                    app_name=app_name,
                    contribution=GroupContribution(role.upper()),
                    effective_role=effective_roles.get(app_id),
                )
                for app_id, app_name, role in rows
            ],
            total=total,
            offset=offset,
            limit=limit,
        )
