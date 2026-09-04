from pydantic import BaseModel, ConfigDict, field_validator
from typing import Literal, Optional, List, Dict, Any
from datetime import datetime
from models.agent import DEFAULT_AGENT_TEMPERATURE, DEFAULT_MEMORY_SUMMARIZE_THRESHOLD

_VALID_RAG_SEARCH_TYPES = {"similarity", "mmr", "similarity_score_threshold"}


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
    created_at: Optional[datetime] = None
    request_count: int
    # OCR-specific fields
    vision_service_id: Optional[int] = None
    vision_system_prompt: Optional[str] = None
    text_system_prompt: Optional[str] = None
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
    marketplace_visibility: Optional[str] = None
    marketplace_profile: Optional[Dict[str, Any]] = None
    is_frozen: bool = False
    # RAG retrieval config (step_008)
    rag_k: Optional[int] = None
    rag_search_type: Optional[str] = None
    rag_score_threshold: Optional[float] = None
    rag_max_retrieval_calls: Optional[int] = None
    rag_fixed_filters: Optional[List[dict]] = None

    model_config = ConfigDict(from_attributes=True)


class CreateUpdateAgentSchema(RagConfigFieldsMixin):
    """Schema for creating or updating an agent"""
    name: str
    description: Optional[str] = ""
    system_prompt: Optional[str] = ""
    prompt_template: Optional[str] = ""
    type: str = "agent"  # "agent", "ocr_agent"
    is_tool: bool = False
    has_memory: bool = False
    enable_code_interpreter: bool = False
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
    # OCR-specific fields
    vision_service_id: Optional[int] = None
    vision_system_prompt: Optional[str] = None
    text_system_prompt: Optional[str] = None


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
