"""Response models for the authenticated user's read-only group access view."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class GroupContribution(str, Enum):
    """A group policy's limited contribution to an app."""

    VIEWER = "VIEWER"
    EDITOR = "EDITOR"


class MyGroupListItem(BaseModel):
    """A directly provisioned group with a current membership."""

    group_id: int
    display_name: str

    model_config = ConfigDict(from_attributes=True)


class MyGroupsPage(BaseModel):
    """A bounded page of the user's eligible groups."""

    items: list[MyGroupListItem]
    total: int
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)

    model_config = ConfigDict(from_attributes=True)


class MyGroupAppListItem(BaseModel):
    """An app, this group's contribution, and the user's overall app role."""

    app_id: int
    app_name: Optional[str] = None
    contribution: GroupContribution
    effective_role: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MyGroupAppsPage(BaseModel):
    """A bounded app page for one eligible group, possibly with no app policies."""

    group_id: int
    display_name: str
    items: list[MyGroupAppListItem]
    total: int
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)

    model_config = ConfigDict(from_attributes=True)
