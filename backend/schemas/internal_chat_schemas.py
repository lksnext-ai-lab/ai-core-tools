"""Schemas of the flexible per-App Chat (spec ``app-flexible-chat``, AD-4 / AD-8).

Step 7 only needs the selection, the per-turn snapshot (``ChatTurnInfo``) and the options payload;
the request/response schemas of the HTTP endpoints are added by the router step.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

MAX_SELECTION_ITEMS = 50

SiloSourceType = Literal["repository", "domain", "sharepoint", "silo"]
WarningKind = Literal["ai_service", "silo", "skill", "mcp_config"]


class ChatSelection(BaseModel):
    """What the user picks for one turn."""

    model_config = ConfigDict(extra="forbid")

    ai_service_id: int
    silo_id: Optional[int] = None
    skill_ids: list[int] = Field(default_factory=list, max_length=MAX_SELECTION_ITEMS)
    mcp_config_ids: list[int] = Field(default_factory=list, max_length=MAX_SELECTION_ITEMS)


class ChatSelectionWarning(BaseModel):
    """A stored default / conversation selection entry that is no longer valid and was dropped."""

    kind: WarningKind
    id: int


class ChatTurnRef(BaseModel):
    """A skill / MCP config as it was used by a turn; ``deleted`` when it no longer exists."""

    id: int
    name: str
    deleted: bool = False


class ChatTurnInfo(BaseModel):
    """Effective configuration of one assistant message (allow-listed; never an ORM dump)."""

    turn_index: int
    ai_service_id: Optional[int] = None
    ai_service_name: str
    ai_service_deleted: bool = False
    silo_id: Optional[int] = None
    silo_name: Optional[str] = None
    silo_deleted: bool = False
    skills: list[ChatTurnRef] = Field(default_factory=list)
    mcp_configs: list[ChatTurnRef] = Field(default_factory=list)
    created_at: datetime
    # Selected resources that were skipped for this turn (e.g. an MCP config with an unusable connection
    # config). Only filled in the payload of the turn that has just completed; never in history.
    warnings: list[ChatSelectionWarning] = Field(default_factory=list)


class ChatAIServiceOption(BaseModel):
    service_id: int
    name: str
    provider: Optional[str] = None
    model_name: Optional[str] = None
    is_system: bool
    lifecycle_status: str
    end_of_service_at: Optional[datetime] = None
    deprecation_notice: Optional[str] = None


class ChatSiloOption(BaseModel):
    silo_id: int
    name: Optional[str] = None
    source_type: SiloSourceType
    source_name: Optional[str] = None
    disabled_reason: Optional[Literal["embedding_service_retired"]] = None


class ChatSkillOption(BaseModel):
    skill_id: int
    name: str
    description: Optional[str] = None
    is_system: bool


class ChatMcpConfigOption(BaseModel):
    config_id: int
    name: str


class ChatOptionsResponse(BaseModel):
    ai_services: list[ChatAIServiceOption]
    silos: list[ChatSiloOption]
    skills: list[ChatSkillOption]
    mcp_configs: list[ChatMcpConfigOption]
    default_selection: Optional[ChatSelection] = None
    default_warnings: list[ChatSelectionWarning] = Field(default_factory=list)
    has_usable_model: bool
