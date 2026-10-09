import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal, Optional, List, Dict, Any
from datetime import datetime
from models.agent import DEFAULT_AGENT_TEMPERATURE, DEFAULT_MEMORY_SUMMARIZE_THRESHOLD

_VALID_RAG_SEARCH_TYPES = {"similarity", "mmr", "similarity_score_threshold"}

_A2A_NAME_MAX_LEN = 255
_A2A_DESCRIPTION_MAX_LEN = 1000
_A2A_MAX_TAGS = 20
_A2A_TAG_MAX_LEN = 50
_A2A_MAX_EXAMPLES = 20
_A2A_EXAMPLE_MAX_LEN = 500
# Raw-list caps applied before dedupe/trim, so a caller can't force an expensive
# per-item normalization pass with an oversized payload. The user-facing cap
# (post-dedupe) stays 20; this is only a cheap upfront guard.
_A2A_RAW_LIST_MAX_LEN = 100
_VALID_A2A_CARD_VISIBILITY = {"public", "api_key"}

# Unicode categories rejected by clean_a2a_text: Cc (control) and Cf (format,
# e.g. zero-width/bidi-override characters). NUL (U+0000) is category Cc and is
# always rejected. \n and \t are Cc too, so they're allowed explicitly where the
# caller opts in via allow_newline/allow_tab.
_REJECTED_UNICODE_CATEGORIES = {"Cc", "Cf"}


def clean_a2a_text(value: str, *, allow_newline: bool = False, allow_tab: bool = False) -> str:
    """Reject NUL and other Unicode control/format characters from free text.

    Shared by every A2A text field (name/description overrides, each skill tag,
    each example) so the hygiene rule is defined exactly once. Exported for
    step_010's export/import validators to reuse rather than duplicate.

    Args:
        value: The already-stripped string to check.
        allow_newline: When True, ``\\n`` is not rejected (used by descriptions
            and examples, never by the single-line name override or tags).
        allow_tab: When True, ``\\t`` is not rejected.

    Returns:
        The input string, unchanged, if it contains no disallowed character.

    Raises:
        ValueError: If the string contains NUL or another Cc/Cf character not
            explicitly allowed.
    """
    for ch in value:
        if ch == "\n" and allow_newline:
            continue
        if ch == "\t" and allow_tab:
            continue
        if unicodedata.category(ch) in _REJECTED_UNICODE_CATEGORIES:
            raise ValueError("must not contain control or non-printable characters")
    return value


class A2AAgentFieldsMixin(BaseModel):
    """Shared A2A (Agent2Agent protocol) per-agent fields + validators (step_009, FR-3).

    Mixed into the agent create/update and read schemas so the field set, caps and
    normalization are defined exactly once. Not exposed on the public API schemas
    (``PublicAgentSchema``, ``PublicAgentDetailSchema``): A2A config is edited only
    through the internal agent API.

    Also mixed into ``schemas.export_schemas.ExportAgentSchema`` (step_010, FR-24,
    AC-39), so export/import reuse these exact caps and validators instead of
    duplicating them. Import treats the file as untrusted input and always forces
    ``a2a_enabled=False`` after validation, but that forcing happens in
    ``AgentImportService`` (see ``_a2a_import_fields``), never in this mixin or in
    ``ExportAgentSchema`` itself, so the schema stays a faithful round-trip of
    whatever the file actually contains.

    ``a2a_enabled`` and ``a2a_card_visibility`` are intentionally **not** ``Optional``:
    there is no "unset" meaning for either (FR-3 defines them as bool / a 2-value
    enum with a default), so an explicit JSON ``null`` must be a 422, never silently
    coerced to the default. Omitting the key entirely (vs. sending it) is handled by
    the router via ``model_fields_set``, so a partial update that never mentions A2A
    fields leaves the persisted values untouched instead of resetting them.
    """
    a2a_enabled: bool = False
    a2a_card_visibility: Literal["public", "api_key"] = "public"
    a2a_name_override: Optional[str] = None
    a2a_description_override: Optional[str] = None
    a2a_skill_tags: Optional[List[str]] = Field(default_factory=list, max_length=_A2A_RAW_LIST_MAX_LEN)
    a2a_examples: Optional[List[str]] = Field(default_factory=list, max_length=_A2A_RAW_LIST_MAX_LEN)

    @field_validator("a2a_name_override")
    @classmethod
    def _validate_a2a_name_override(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > _A2A_NAME_MAX_LEN:
            raise ValueError(f"a2a_name_override must be at most {_A2A_NAME_MAX_LEN} characters")
        return clean_a2a_text(v)

    @field_validator("a2a_description_override")
    @classmethod
    def _validate_a2a_description_override(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > _A2A_DESCRIPTION_MAX_LEN:
            raise ValueError(
                f"a2a_description_override must be at most {_A2A_DESCRIPTION_MAX_LEN} characters"
            )
        return clean_a2a_text(v, allow_newline=True, allow_tab=True)

    @field_validator("a2a_skill_tags")
    @classmethod
    def _validate_a2a_skill_tags(cls, v: Optional[List[str]]) -> List[str]:
        if not v:
            return []
        seen: set = set()
        result: List[str] = []
        for raw in v:
            tag = (raw or "").strip()
            if not tag:
                continue
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(clean_a2a_text(tag))
        if len(result) > _A2A_MAX_TAGS:
            raise ValueError(f"a2a_skill_tags must have at most {_A2A_MAX_TAGS} items")
        for tag in result:
            if len(tag) > _A2A_TAG_MAX_LEN:
                raise ValueError(f"each a2a_skill_tags item must be at most {_A2A_TAG_MAX_LEN} characters")
        return result

    @field_validator("a2a_examples")
    @classmethod
    def _validate_a2a_examples(cls, v: Optional[List[str]]) -> List[str]:
        if not v:
            return []
        result = [
            clean_a2a_text(ex.strip(), allow_newline=True, allow_tab=True)
            for ex in v if ex and ex.strip()
        ]
        if len(result) > _A2A_MAX_EXAMPLES:
            raise ValueError(f"a2a_examples must have at most {_A2A_MAX_EXAMPLES} items")
        for example in result:
            if len(example) > _A2A_EXAMPLE_MAX_LEN:
                raise ValueError(
                    f"each a2a_examples item must be at most {_A2A_EXAMPLE_MAX_LEN} characters"
                )
        return result


class RagConfigFieldsMixin(BaseModel):
    """Shared per-agent RAG retrieval-config fields + validators (step_008).

    Mixed into the agent create/update request schemas so the field set and the
    validation bounds are defined exactly once. Values are persisted on the Agent
    model; precedence (caller > agent > system) is resolved at execution time by
    ``resolve_search_params``.
    """
    rag_k: Optional[int] = None
    rag_search_type: Optional[str] = None
    rag_score_threshold: Optional[float] = None
    rag_max_retrieval_calls: Optional[int] = None
    rag_fixed_filters: Optional[List[dict]] = None

    @field_validator("rag_k")
    @classmethod
    def validate_rag_k(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 100):
            raise ValueError("rag_k must be between 1 and 100")
        return v

    @field_validator("rag_search_type")
    @classmethod
    def validate_rag_search_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_RAG_SEARCH_TYPES:
            raise ValueError(f"rag_search_type must be one of {sorted(_VALID_RAG_SEARCH_TYPES)}")
        return v

    @field_validator("rag_score_threshold")
    @classmethod
    def validate_rag_score_threshold(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError("rag_score_threshold must be between 0 and 1")
        return v

    @field_validator("rag_max_retrieval_calls")
    @classmethod
    def validate_rag_max_retrieval_calls(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 20):
            raise ValueError("rag_max_retrieval_calls must be between 1 and 20")
        return v

    @field_validator("rag_fixed_filters")
    @classmethod
    def validate_rag_fixed_filters(cls, v: Optional[List[dict]]) -> Optional[List[dict]]:
        if v is None:
            return v
        from tools.vector_stores.metadata_filters import MetadataFilterClause
        validated: List[dict] = []
        for elem in v:
            clause = MetadataFilterClause(**elem)
            validated.append(clause.model_dump())
        return validated


class RuntimeSearchParamsSchema(BaseModel):
    """Bounds for caller-supplied runtime search params on the public chat API.

    Acts as a validation gate only: a DoS guard so an API-key holder cannot force a
    huge retrieval (k/fetch_k) per turn. Tuning fields share the agent-config bounds;
    `filter` values are whitelisted later in the retrieval pipeline. Unknown keys are
    ignored here (they are dropped by ``resolve_search_params`` anyway).
    """
    k: Optional[int] = None
    search_type: Optional[str] = None
    score_threshold: Optional[float] = None
    fetch_k: Optional[int] = None
    lambda_mult: Optional[float] = None
    filter: Optional[Dict[str, Any]] = None

    @field_validator("k", "fetch_k")
    @classmethod
    def validate_positive_k(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 100):
            raise ValueError("must be between 1 and 100")
        return v

    @field_validator("search_type")
    @classmethod
    def validate_search_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_RAG_SEARCH_TYPES:
            raise ValueError(f"must be one of {sorted(_VALID_RAG_SEARCH_TYPES)}")
        return v

    @field_validator("score_threshold", "lambda_mult")
    @classmethod
    def validate_unit_interval(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError("must be between 0 and 1")
        return v

# ==================== AGENT SCHEMAS ====================

class AgentListItemSchema(BaseModel):
    """Schema for agent list items"""
    agent_id: int
    name: str
    description: Optional[str] = None
    type: str  # "agent", "ocr_agent", etc.
    is_tool: bool
    created_at: Optional[datetime] = None
    request_count: int
    service_id: Optional[int] = None
    ai_service: Optional[Dict[str, Any]] = None  # AI service details
    marketplace_visibility: Optional[str] = None
    is_frozen: bool = False
    a2a_enabled: bool = False

    model_config = ConfigDict(from_attributes=True)


class AgentDetailSchema(BaseModel):
    """Schema for detailed agent information"""
    agent_id: int
    name: str
    description: str
    system_prompt: str
    prompt_template: str
    type: str
    is_tool: bool
    has_memory: bool
    enable_code_interpreter: bool = False
    skill_router_enabled: bool = False
    server_tools: List[str] = []
    memory_max_messages: int = 20
    memory_max_tokens: Optional[int] = 4000
    memory_summarize_threshold: int = DEFAULT_MEMORY_SUMMARIZE_THRESHOLD
    service_id: Optional[int] = None
    sandbox_service_id: Optional[int] = None
    silo_id: Optional[int] = None
    output_parser_id: Optional[int] = None
    temperature: float = DEFAULT_AGENT_TEMPERATURE
    tool_ids: List[int] = []
    mcp_config_ids: List[int] = []
    skill_ids: List[int] = []
    middleware_ids: List[int] = []
    created_at: Optional[datetime] = None
    request_count: int
    # OCR-specific fields
    vision_service_id: Optional[int] = None
    vision_system_prompt: Optional[str] = None
    text_system_prompt: Optional[str] = None
    # Media processing configuration (playground media upload)
    transcription_service_id: Optional[int] = None
    video_ai_service_id: Optional[int] = None
    media_embedding_service_id: Optional[int] = None
    media_forced_language: Optional[str] = None
    media_chunk_min_duration: int = 30
    media_chunk_max_duration: int = 120
    media_chunk_overlap: int = 5
    # Silo information for playground
    silo: Optional[Dict[str, Any]] = None
    # Output parser information for playground
    output_parser: Optional[Dict[str, Any]] = None
    # Form data for editing
    ai_services: List[Dict[str, Any]]
    sandbox_services: List[Dict[str, Any]]
    silos: List[Dict[str, Any]]
    output_parsers: List[Dict[str, Any]]
    tools: List[Dict[str, Any]]
    mcp_configs: List[Dict[str, Any]]
    skills: List[Dict[str, Any]]
    middlewares: List[Dict[str, Any]] = []
    marketplace_visibility: Optional[str] = None
    marketplace_profile: Optional[Dict[str, Any]] = None
    is_frozen: bool = False
    # RAG retrieval config (step_008)
    rag_k: Optional[int] = None
    rag_search_type: Optional[str] = None
    rag_score_threshold: Optional[float] = None
    rag_max_retrieval_calls: Optional[int] = None
    rag_fixed_filters: Optional[List[dict]] = None
    # A2A (Agent2Agent protocol) configuration (step_009, FR-3)
    a2a_enabled: bool = False
    a2a_card_visibility: Literal["public", "api_key"] = "public"
    a2a_name_override: Optional[str] = None
    a2a_description_override: Optional[str] = None
    a2a_skill_tags: List[str] = []
    a2a_examples: List[str] = []
    a2a_card_url: Optional[str] = None
    a2a_rpc_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CreateUpdateAgentSchema(RagConfigFieldsMixin, A2AAgentFieldsMixin):
    """Schema for creating or updating an agent"""
    name: str
    description: Optional[str] = ""
    system_prompt: Optional[str] = ""
    prompt_template: Optional[str] = ""
    type: str = "agent"  # "agent", "ocr_agent"
    is_tool: bool = False
    has_memory: bool = False
    enable_code_interpreter: bool = False
    skill_router_enabled: bool = False
    server_tools: Optional[List[str]] = []
    memory_max_messages: Optional[int] = 20
    memory_max_tokens: Optional[int] = 4000
    memory_summarize_threshold: Optional[int] = DEFAULT_MEMORY_SUMMARIZE_THRESHOLD
    service_id: Optional[int] = None
    sandbox_service_id: Optional[int] = None
    silo_id: Optional[int] = None
    output_parser_id: Optional[int] = None
    temperature: Optional[float] = DEFAULT_AGENT_TEMPERATURE
    tool_ids: Optional[List[int]] = []
    mcp_config_ids: Optional[List[int]] = []
    skill_ids: Optional[List[int]] = []
    # None = leave the agent's middlewares untouched; a list replaces them (order = chain order).
    middleware_ids: Optional[List[int]] = None
    # OCR-specific fields
    vision_service_id: Optional[int] = None
    vision_system_prompt: Optional[str] = None
    text_system_prompt: Optional[str] = None
    # Media processing configuration (playground media upload)
    transcription_service_id: Optional[int] = None
    video_ai_service_id: Optional[int] = None
    # Optional embedding service used to vectorize media/documents into the
    # session's temp playground silo. Agents that do not use media/document
    # processing do not need to configure one.
    media_embedding_service_id: Optional[int] = None
    media_forced_language: Optional[str] = None
    media_chunk_min_duration: Optional[int] = Field(default=30, ge=1, le=3600)
    media_chunk_max_duration: Optional[int] = Field(default=120, ge=1, le=3600)
    media_chunk_overlap: Optional[int] = Field(default=5, ge=0, le=600)

    @model_validator(mode="after")
    def _validate_media_config(self) -> "CreateUpdateAgentSchema":
        mn = self.media_chunk_min_duration
        mx = self.media_chunk_max_duration
        ov = self.media_chunk_overlap
        if mn is not None and mx is not None and mn > mx:
            raise ValueError(
                "media_chunk_min_duration must not exceed media_chunk_max_duration"
            )
        if ov is not None and mx is not None and ov >= mx:
            raise ValueError(
                "media_chunk_overlap must be smaller than media_chunk_max_duration"
            )
        return self


class UpdatePromptSchema(BaseModel):
    """Schema for updating agent prompts"""
    type: str  # "system" or "template"
    prompt: str


# ==================== PUBLIC API SCHEMAS ====================

class PublicAgentSchema(BaseModel):
    """Public agent schema for API responses"""
    model_config = ConfigDict(from_attributes=True)
    
    agent_id: int
    name: str
    description: Optional[str] = None
    type: str
    status: Optional[str] = None
    is_tool: bool
    has_memory: Optional[bool] = None
    create_date: Optional[datetime] = None
    request_count: int


class PublicAgentDetailSchema(BaseModel):
    """Detailed public agent schema for API responses"""
    model_config = ConfigDict(from_attributes=True)

    agent_id: int
    name: str
    description: Optional[str] = None
    type: str
    status: Optional[str] = None
    is_tool: bool
    has_memory: Optional[bool] = None
    memory_max_messages: Optional[int] = 20
    memory_max_tokens: Optional[int] = 4000
    memory_summarize_threshold: Optional[int] = DEFAULT_MEMORY_SUMMARIZE_THRESHOLD
    system_prompt: Optional[str] = None
    prompt_template: Optional[str] = None
    create_date: Optional[datetime] = None
    request_count: int
    service_id: Optional[int] = None
    silo_id: Optional[int] = None
    output_parser_id: Optional[int] = None
    temperature: Optional[float] = DEFAULT_AGENT_TEMPERATURE
    # OCR-specific fields
    vision_service_id: Optional[int] = None
    vision_system_prompt: Optional[str] = None
    text_system_prompt: Optional[str] = None
    # RAG retrieval config (step_008)
    rag_k: Optional[int] = None
    rag_search_type: Optional[str] = None
    rag_score_threshold: Optional[float] = None
    rag_max_retrieval_calls: Optional[int] = None
    rag_fixed_filters: Optional[List[dict]] = None


class CreateAgentRequestSchema(RagConfigFieldsMixin):
    """Schema for creating a new agent via public API"""
    name: str
    description: Optional[str] = ""
    type: Literal["agent"] = "agent"
    is_tool: bool = False
    has_memory: bool = False
    memory_max_messages: Optional[int] = 20
    memory_max_tokens: Optional[int] = 4000
    memory_summarize_threshold: Optional[int] = DEFAULT_MEMORY_SUMMARIZE_THRESHOLD
    system_prompt: Optional[str] = ""
    prompt_template: Optional[str] = ""
    service_id: Optional[int] = None
    silo_id: Optional[int] = None
    output_parser_id: Optional[int] = None
    temperature: Optional[float] = DEFAULT_AGENT_TEMPERATURE
    tool_ids: Optional[List[int]] = []
    mcp_config_ids: Optional[List[int]] = []
    skill_ids: Optional[List[int]] = []


class CreateOCRAgentRequestSchema(BaseModel):
    """Schema for creating a new OCR agent via public API"""
    name: str
    description: Optional[str] = ""
    is_tool: bool = False
    has_memory: bool = False
    memory_max_messages: Optional[int] = 20
    memory_max_tokens: Optional[int] = 4000
    memory_summarize_threshold: Optional[int] = DEFAULT_MEMORY_SUMMARIZE_THRESHOLD
    service_id: Optional[int] = None
    vision_service_id: Optional[int] = None
    vision_system_prompt: Optional[str] = ""
    text_system_prompt: Optional[str] = ""
    output_parser_id: Optional[int] = None
    temperature: Optional[float] = DEFAULT_AGENT_TEMPERATURE
    tool_ids: Optional[List[int]] = []
    mcp_config_ids: Optional[List[int]] = []
    skill_ids: Optional[List[int]] = []


class UpdateAgentRequestSchema(RagConfigFieldsMixin):
    """Schema for updating an existing agent via public API"""
    name: Optional[str] = None
    description: Optional[str] = None
    is_tool: Optional[bool] = None
    has_memory: Optional[bool] = None
    memory_max_messages: Optional[int] = None
    memory_max_tokens: Optional[int] = None
    memory_summarize_threshold: Optional[int] = None
    system_prompt: Optional[str] = None
    prompt_template: Optional[str] = None
    service_id: Optional[int] = None
    silo_id: Optional[int] = None
    output_parser_id: Optional[int] = None
    temperature: Optional[float] = None
    tool_ids: Optional[List[int]] = None
    mcp_config_ids: Optional[List[int]] = None
    skill_ids: Optional[List[int]] = None


class UpdateOCRAgentRequestSchema(BaseModel):
    """Schema for updating an existing OCR agent via public API"""
    name: Optional[str] = None
    description: Optional[str] = None
    is_tool: Optional[bool] = None
    has_memory: Optional[bool] = None
    memory_max_messages: Optional[int] = None
    memory_max_tokens: Optional[int] = None
    memory_summarize_threshold: Optional[int] = None
    service_id: Optional[int] = None
    vision_service_id: Optional[int] = None
    vision_system_prompt: Optional[str] = None
    text_system_prompt: Optional[str] = None
    output_parser_id: Optional[int] = None
    temperature: Optional[float] = None
    tool_ids: Optional[List[int]] = None
    mcp_config_ids: Optional[List[int]] = None
    skill_ids: Optional[List[int]] = None


class PublicAgentsResponseSchema(BaseModel):
    """Multiple agents response for public API"""
    agents: List[PublicAgentSchema]


class PublicAgentResponseSchema(BaseModel):
    """Single agent response for public API"""
    agent: PublicAgentDetailSchema
