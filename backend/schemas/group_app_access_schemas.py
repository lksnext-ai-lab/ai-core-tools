"""Schemas for explicit external-group app access policies."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from models.group_app_access_rule import GroupAppAccessRole


class GroupAppAccessRuleCreate(BaseModel):
    """Create or reactivate a group access policy."""

    group_id: int
    role: GroupAppAccessRole


class GroupAppAccessRuleUpdate(BaseModel):
    """Change a group access policy without deleting its audit row."""

    role: Optional[GroupAppAccessRole] = None
    is_active: Optional[bool] = None


class GroupAppAccessRuleDetail(BaseModel):
    """A complete group access policy returned by the internal API."""

    id: int
    group_id: int
    app_id: int
    role: GroupAppAccessRole
    created_by_user_id: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    group_display_name: str
    connection_id: int

    model_config = ConfigDict(from_attributes=True)


class GroupAppAccessRuleListItem(GroupAppAccessRuleDetail):
    """A group access policy in an app policy list."""


class GroupAppEffectiveAccess(BaseModel):
    """Effective group-derived access for a user and app."""

    app_id: int
    role: Optional[GroupAppAccessRole] = None

    model_config = ConfigDict(from_attributes=True)
