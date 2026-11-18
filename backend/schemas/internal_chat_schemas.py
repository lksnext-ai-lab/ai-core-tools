"""Schemas of the flexible per-App Chat.

Selection, per-turn snapshot (``ChatTurnInfo``) and options payload come first; the request/response
schemas of the HTTP endpoints (conversations, messages, defaults) follow. Responses never carry the
``session_id`` or the internal ``agent_id``: both stay server-side.
"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

MAX_SELECTION_ITEMS = 50

SiloSourceType = Literal["repository", "domain", "sharepoint", "silo"]
# ``sandbox_output``: ``id`` is the number of sandbox output files that could not be delivered this turn.
WarningKind = Literal["ai_service", "silo", "skill", "mcp_config", "sandbox_output"]


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


class ChatAttachmentIndexing(BaseModel):
    """Whether Chat attachments are indexed (RAG) or sent in the prompt; ``reason`` explains a disabled state."""

    enabled: bool
    reason: Optional[Literal["no_default_embedding_service", "embedding_service_retired"]] = None


class ChatCodeInterpreter(BaseModel):
    """Whether the Chat has a code interpreter (the App's default sandbox service); ``reason`` explains a disabled state."""

    enabled: bool
    reason: Optional[
        Literal[
            "disabled_in_app_settings",
            "sandbox_service_retired",
            "sandbox_provider_unavailable",
        ]
    ] = None


class ChatOptionsResponse(BaseModel):
    ai_services: list[ChatAIServiceOption]
    silos: list[ChatSiloOption]
    skills: list[ChatSkillOption]
    mcp_configs: list[ChatMcpConfigOption]
    default_selection: Optional[ChatSelection] = None
    default_warnings: list[ChatSelectionWarning] = Field(default_factory=list)
    has_usable_model: bool
    attachment_indexing: ChatAttachmentIndexing = Field(
        default_factory=lambda: ChatAttachmentIndexing(enabled=False, reason="no_default_embedding_service")
    )
    code_interpreter: ChatCodeInterpreter = Field(
        default_factory=lambda: ChatCodeInterpreter(enabled=False, reason="disabled_in_app_settings")
    )


MAX_TITLE_LENGTH = 255  # Conversation.title is String(255)


class ChatConversationCreate(BaseModel):
    """Create a Chat conversation; without ``selection`` the user's default (or the App default) is used."""

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, max_length=MAX_TITLE_LENGTH)
    selection: Optional[ChatSelection] = None


class ChatConversationRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)


class ChatConversationResponse(BaseModel):
    """One Chat conversation of the caller. ``selection`` is only filled by the create endpoint."""

    model_config = ConfigDict(from_attributes=True)

    conversation_id: int
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_message: Optional[str] = None
    message_count: int = 0
    selection: Optional[ChatSelection] = None


class ChatConversationListResponse(BaseModel):
    conversations: list[ChatConversationResponse]
    total: int


class ChatHistoryMessage(BaseModel):
    """A message of the history; assistant messages carry the ``turn`` snapshot (null when unknown)."""

    role: str
    content: str
    message_id: Optional[str] = None
    turn: Optional[ChatTurnInfo] = None


class ChatConversationDetailResponse(ChatConversationResponse):
    """A conversation with its history (as kept by the checkpointer, already summarized when long)."""

    messages: list[ChatHistoryMessage] = Field(default_factory=list)
    current_selection: Optional[ChatSelection] = None
    warnings: list[ChatSelectionWarning] = Field(default_factory=list)
    # Approval the conversation is paused on (only visible to its requester); the Chat itself rejects pauses.
    pending_approval: Optional[dict[str, Any]] = None


class ChatMessageResponse(BaseModel):
    """Answer of the synchronous ``POST /chat/messages``."""

    response: str | dict[str, Any]
    conversation_id: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    # None when the completion hook skipped or failed (the answer is still valid).
    turn: Optional[ChatTurnInfo] = None


class ChatFileUploadResponse(BaseModel):
    """Same keys as the playground upload response."""

    success: bool
    file_id: str
    filename: str
    file_type: Optional[str] = None
    vectorized: bool
    file_size_bytes: Optional[int] = None
    file_size_display: Optional[str] = None
    processing_status: Optional[str] = None
    content_preview: Optional[str] = None
    has_extractable_content: Optional[bool] = None
    mime_type: Optional[str] = None


class ChatFileInfo(BaseModel):
    """One attached file, as ``FileReference.to_dict()`` reports it."""

    file_id: str
    filename: str
    file_type: Optional[str] = None
    content: Optional[str] = None
    file_path: Optional[str] = None
    uploaded_at: Optional[str] = None
    file_size_bytes: Optional[int] = None
    file_size_display: Optional[str] = None
    processing_status: Optional[str] = None
    content_preview: Optional[str] = None
    has_extractable_content: Optional[bool] = None
    mime_type: Optional[str] = None
    conversation_id: Optional[str] = None


class ChatFileListResponse(BaseModel):
    files: list[ChatFileInfo]
    total_size_bytes: int
    total_size_display: str


class ChatFileDownloadResponse(BaseModel):
    download_url: str
    filename: str
