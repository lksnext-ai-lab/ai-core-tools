from enum import Enum
from typing import List, Optional, Set, Union
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from lks_idprovider import AuthContext

from db.database import get_db
from models.app import App
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from routers.internal.auth_utils import get_current_user_oauth
from utils.config import is_omniadmin
from utils.logger import get_logger

logger = get_logger(__name__)

class AppRole(str, Enum):
    OMNIADMIN = "omniadmin"
    OWNER = "owner"
    ADMINISTRATOR = "administrator"
    EDITOR = "editor"
    VIEWER = "viewer"
    USER = "user"   # Authenticated but no app affiliation
    GUEST = "guest" # Not authenticated

# Hierarchy: higher index = higher privilege
ROLE_HIERARCHY = [
    AppRole.GUEST,
    AppRole.USER,
    AppRole.VIEWER,
    AppRole.EDITOR,
    AppRole.ADMINISTRATOR,
    AppRole.OWNER,
    AppRole.OMNIADMIN
]

def get_role_level(role: AppRole) -> int:
    return ROLE_HIERARCHY.index(role)

def resolve_user_app_role(
    db: Session,
    app_id: int,
    user_id: Optional[int] = None,
    email: Optional[str] = None
) -> Optional[AppRole]:
    """
    Resolve the effective role of a user for a specific app.
    Returns None if the app does not exist.
    """
    # 1. Check Omniadmin
    if email and is_omniadmin(email):
        return AppRole.OMNIADMIN

    # If not authenticated (no user_id), return GUEST
    if not user_id:
        return AppRole.GUEST

    # 2. Check App existence
    app = db.query(App).filter(App.app_id == app_id).first()
    if not app:
        return None

    # 3. Check Ownership
    if app.owner_id == user_id:
        return AppRole.OWNER

    # 4. Check Collaboration
    collaboration = db.query(AppCollaborator).filter(
        AppCollaborator.app_id == app_id,
        AppCollaborator.user_id == user_id,
        AppCollaborator.status == CollaborationStatus.ACCEPTED
    ).first()

    if collaboration:
        # Map CollaborationRole to AppRole
        try:
            # Direct mapping if names match
            return AppRole(collaboration.role.value)
        except ValueError:
            # Fallback or specific mapping if needed
            if collaboration.role == CollaborationRole.ADMINISTRATOR:
                return AppRole.ADMINISTRATOR
            elif collaboration.role == CollaborationRole.EDITOR:
                return AppRole.EDITOR
            elif collaboration.role == CollaborationRole.OWNER:
                return AppRole.OWNER
            
            logger.warning(f"Unknown collaboration role: {collaboration.role}")
            return AppRole.USER

    # 5. Authenticated but no affiliation
    return AppRole.USER

def has_min_role(user_role: AppRole, required_role: AppRole) -> bool:
    return get_role_level(user_role) >= get_role_level(required_role)

def has_any_role(user_role: AppRole, allowed_roles: Set[AppRole]) -> bool:
    if user_role == AppRole.OMNIADMIN:
        return True
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
        email = auth_context.identity.email

        role = resolve_user_app_role(db, app_id, user_id, email)

        if role is None:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")

        if self.required_min_role:
            if not has_min_role(role, self.required_min_role):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions"
                )
        
        if self.allowed_roles:
            if not has_any_role(role, self.allowed_roles):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions"
                )
        
        return role

def require_min_role(role: Union[AppRole, str]):
    if isinstance(role, str):
        role = AppRole(role)
    return RoleChecker(required_min_role=role)

def require_any_role(roles: Set[Union[AppRole, str]]):
    resolved_roles = set()
    for r in roles:
        if isinstance(r, str):
            resolved_roles.add(AppRole(r))
        else:
            resolved_roles.add(r)
    return RoleChecker(allowed_roles=resolved_roles)
