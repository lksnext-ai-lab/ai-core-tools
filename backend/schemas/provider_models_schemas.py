from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ==================== PROVIDER MODELS DISCOVERY SCHEMAS ====================


class ProviderCapabilities(BaseModel):
    """Capability flags exposed for a single provider model.

    These flags drive both server-side filtering (chat vs embedding) and
    client-side filter chips (vision, function calling, ...). Flags should
    be set conservatively: when the source SDK does not expose a capability
    explicitly, leave it false rather than guessing optimistically.
    """

    chat: bool = False
    embedding: bool = False
    vision: bool = False
    audio: bool = False  # speech-to-text or text-to-speech
    function_calling: bool = False
    tool_use: bool = False
    reasoning: bool = False  # o-series, claude thinking, gemini thinking
    json_mode: bool = False

    model_config = ConfigDict(from_attributes=True)


ModelInfoSource = Literal["api", "catalog", "heuristic"]


class ProviderModelInfo(BaseModel):
    """Normalised model metadata returned by the provider listing endpoint.

    `id` is the canonical identifier the platform stores in
    ``AIService.description`` / ``EmbeddingService.description``.
    `source` records where each piece of information came from so the
    frontend can warn the user when capabilities are inferred rather than
    confirmed by the provider. ``created_at`` is a Unix timestamp used to
    sort the listing so the most recent models appear first.
    """

    id: str
    display_name: str
    family: Optional[str] = None
    capabilities: ProviderCapabilities = Field(default_factory=ProviderCapabilities)
    context_window: Optional[int] = None
    owned_by: Optional[str] = None
    deprecated: bool = False
    created_at: Optional[int] = None
    source: ModelInfoSource = "api"

    model_config = ConfigDict(from_attributes=True)


ListPurpose = Literal["chat", "embedding"]


class ListProviderModelsRequest(BaseModel):
    """Request body for the ``POST .../list-models`` endpoints.

    The endpoints intentionally take the credentials in the payload so the
    user can list models before a service exists in the database. The
    server-side handler forces ``purpose`` to match the route (chat for AI
    services, embedding for embedding services) so the client cannot
    request the wrong list.
    """

    provider: str
    api_key: str = ""
    base_url: Optional[str] = ""
    api_version: Optional[str] = None
    purpose: ListPurpose = "chat"

    @field_validator("api_key", "base_url", mode="before")
    @classmethod
    def _strip_credentials(cls, v):
        return v.strip() if isinstance(v, str) else v


class ListProviderModelsResponse(BaseModel):
    """Response body for the provider listing endpoints."""

    provider: str
    models: List[ProviderModelInfo] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    requires_manual_input: bool = False
