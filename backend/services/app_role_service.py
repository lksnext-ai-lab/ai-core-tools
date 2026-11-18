"""Resolve effective app roles from independent access sources."""

from typing import Optional

from sqlalchemy.orm import Session

from models.app import App
from repositories.app_role_repository import AppRoleRepository, AppRoleSource


ROLE_HIERARCHY = ("guest", "user", "viewer", "editor", "administrator", "owner")


class AppRoleService:
    """Resolve effective user roles without materializing group grants."""

    def __init__(self, db: Session) -> None:
        """Create a role resolver bound to the request's database session."""
        self.repository = AppRoleRepository(db)

    def get_effective_role(self, user_id: int, app_id: int) -> Optional[str]:
        """Return one user's effective role for an app, or ``None`` if absent."""
        return self.get_effective_roles(user_id, [app_id]).get(app_id)

    def get_effective_roles(self, user_id: int, app_ids: list[int]) -> dict[int, str]:
        """Resolve roles for multiple apps with bounded, batched database queries."""
        scoped_app_ids = list(dict.fromkeys(app_id for app_id in app_ids if app_id > 0))
        if not user_id or user_id <= 0 or not scoped_app_ids:
            return {}

        sources = self.repository.get_app_role_sources(user_id, scoped_app_ids)
        return self._combine_role_sources(user_id, sources)

    def get_accessible_apps_with_roles(
        self, user_id: int, limit: Optional[int] = None, offset: int = 0
    ) -> tuple[list[App], dict[int, str], bool]:
        """Return a paginated, ordered app page and its current effective roles."""
        sources, has_more = self.repository.get_accessible_app_role_sources(
            user_id, limit, offset
        )
        roles = self._combine_role_sources(user_id, sources)
        accessible_roles = {
            app_id: role
            for app_id, role in roles.items()
            if ROLE_HIERARCHY.index(role) >= ROLE_HIERARCHY.index("viewer")
        }
        apps_by_id = {
            source.app.app_id: source.app
            for source in sources
            if source.app.app_id in accessible_roles
        }
        return list(apps_by_id.values()), accessible_roles, has_more

    @classmethod
    def _combine_role_sources(
        cls,
        user_id: int,
        sources: list[AppRoleSource],
    ) -> dict[int, str]:
        """Apply the shared app-role hierarchy to repository-provided sources."""
        roles: dict[int, str] = {}
        for source in sources:
            app_id = source.app.app_id
            roles.setdefault(app_id, "user")
            if source.app.owner_id == user_id:
                roles[app_id] = cls._highest_role(roles[app_id], "owner")

            if source.collaboration_role is not None:
                collaboration_role = getattr(
                    source.collaboration_role,
                    "value",
                    str(source.collaboration_role),
                )
                roles[app_id] = cls._highest_role(
                    roles[app_id], collaboration_role
                )

            group_role_name = getattr(source.group_role, "value", source.group_role)
            if group_role_name in {"viewer", "editor"}:
                roles[app_id] = cls._highest_role(roles[app_id], group_role_name)
        return roles

    @staticmethod
    def _highest_role(current_role: str, candidate_role: str) -> str:
        """Select the higher role from the supported app-role hierarchy."""
        if candidate_role not in ROLE_HIERARCHY:
            return current_role
        if ROLE_HIERARCHY.index(candidate_role) > ROLE_HIERARCHY.index(current_role):
            return candidate_role
        return current_role
