from enum import Enum
from typing import Dict, List, Optional, Set
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from lks_idprovider import AuthContext

from db.database import get_db
from routers.internal.auth_utils import get_current_user_oauth
from services.app_role_service import AppRoleService, ROLE_HIERARCHY as ROLE_NAMES
from utils.logger import get_logger

logger = get_logger(__name__)

class AppRole(str, Enum):
    OWNER = "owner"
    ADMINISTRATOR = "administrator"
    EDITOR = "editor"
    VIEWER = "viewer"
    USER = "user"   # Authenticated but no app affiliation
    GUEST = "guest" # Not authenticated

# Hierarchy: higher index = higher privilege
ROLE_HIERARCHY = [AppRole(role) for role in ROLE_NAMES]

def get_role_level(role: AppRole) -> int:
    return ROLE_HIERARCHY.index(role)

def resolve_user_app_role(
    db: Session,
    app_id: int,
    user_id: Optional[int] = None,
) -> Optional[AppRole]:
    """Resolve the current app role from ownership, collaboration, and group policy.

    Platform privileges are independent: this resolver does not elevate platform
    roles or grant platform administration rights. Returns ``None`` if the app
    does not exist.
    """
    if not user_id:
        return AppRole.GUEST

    return resolve_user_app_roles(db, [app_id], user_id).get(app_id)


def resolve_user_app_roles(
    db: Session,
    app_ids: List[int],
    user_id: int,
) -> Dict[int, AppRole]:
    """Resolve effective roles for several apps using batched data access."""
    role_names = AppRoleService(db).get_effective_roles(user_id, app_ids)
    resolved: Dict[int, AppRole] = {}
    for app_id, role_name in role_names.items():
        try:
            resolved[app_id] = AppRole(role_name)
        except ValueError:
            logger.warning("Unknown effective app role: %s", role_name)
            resolved[app_id] = AppRole.USER
    return resolved

def has_min_role(user_role: AppRole, required_role: AppRole) -> bool:
    return get_role_level(user_role) >= get_role_level(required_role)

def has_any_role(user_role: AppRole, allowed_roles: Set[AppRole]) -> bool:
    return user_role in allowed_roles

class RoleChecker:
    def __init__(self, required_min_role: Optional[AppRole] = None, allowed_roles: Optional[Set[AppRole]] = None):
        self.required_min_role = required_min_role
        self.allowed_roles = allowed_roles

    def __call__(
        self,
        app_id: int,
        auth_context: AuthContext = Depends(get_current_user_oauth),
        db: Session = Depends(get_db)
    ):
        user_id = int(auth_context.identity.id) if auth_context.identity.id else None

        role = resolve_user_app_role(db, app_id, user_id)

        if role is None:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")

        if self.required_min_role:
            if not has_min_role(role, self.required_min_role):
                logger.warning(
                    "Denied app authorization user_id=%s app_id=%s role=%s required_role=%s",
                    user_id,
                    app_id,
                    role.value,
                    self.required_min_role.value,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions"
                )
        
        if self.allowed_roles and not has_any_role(role, self.allowed_roles):
            logger.warning(
                "Denied app authorization user_id=%s app_id=%s role=%s allowed_roles=%s",
                user_id,
                app_id,
                role.value,
                sorted(allowed_role.value for allowed_role in self.allowed_roles),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        
        return role

def require_min_role(role: AppRole | str):
    if isinstance(role, str):
        role = AppRole(role)
    return RoleChecker(required_min_role=role)

def require_any_role(roles: Set[AppRole | str]):
    resolved_roles = set()
    for r in roles:
        if isinstance(r, str):
            resolved_roles.add(AppRole(r))
        else:
            resolved_roles.add(r)
    return RoleChecker(allowed_roles=resolved_roles)
