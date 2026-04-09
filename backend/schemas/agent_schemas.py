from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal, Optional, List, Dict, Any
from datetime import datetime
from models.agent import DEFAULT_AGENT_TEMPERATURE

# ==================== AGENT SCHEMAS ====================


class A2AAgentAuthConfigSchema(BaseModel):
    """Authentication configuration for outbound A2A calls."""

    scheme_name: Optional[str] = None
    scheme_type: Literal["none", "apiKey", "http", "oauth2", "openIdConnect", "mtls"] = "none"
    api_key: Optional[str] = None
    bearer_token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    client_certificate: Optional[str] = None
    client_key: Optional[str] = None
    ca_certificate: Optional[str] = None


class A2AAgentSourceConfigSchema(BaseModel):
    """Source linkage payload submitted when importing an A2A agent."""

    card_url: str
    card_snapshot: Optional[Dict[str, Any]] = None
    auth_config: Optional[A2AAgentAuthConfigSchema] = None


class A2AAgentDetailSchema(BaseModel):
    """Persisted A2A metadata returned in agent detail responses."""

    card_url: str
    remote_agent_id: Optional[str] = None
    auth_config: Optional[A2AAgentAuthConfigSchema] = None
    remote_agent_metadata: Dict[str, Any]
    advertised_skills: List[Dict[str, Any]] = Field(default_factory=list)
    sync_status: str
    health_status: str
    last_successful_refresh_at: Optional[datetime] = None
    last_refresh_attempt_at: Optional[datetime] = None
    last_refresh_error: Optional[str] = None
    documentation_url: Optional[str] = None
    icon_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class A2AAgentCardDiscoveryRequestSchema(BaseModel):
    """Request payload for backend-side A2A card discovery."""

    card_url: str


class A2AAgentCardDiscoveryResponseSchema(BaseModel):
    """Discovered A2A card payload returned to the UI."""

    card_url: str
    remote_agent_id: Optional[str] = None
    card: Dict[str, Any]
    skills: List[Dict[str, Any]]
    documentation_url: Optional[str] = None
    icon_url: Optional[str] = None


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
    source_type: Literal["local", "a2a"] = "local"
    health_status: Optional[str] = None
    last_successful_refresh_at: Optional[datetime] = None

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
    memory_summarize_threshold: int = 4000
    service_id: Optional[int] = None
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
    silos: List[Dict[str, Any]]
    output_parsers: List[Dict[str, Any]]
    tools: List[Dict[str, Any]]
    mcp_configs: List[Dict[str, Any]]
    skills: List[Dict[str, Any]]
    marketplace_visibility: Optional[str] = None
    marketplace_profile: Optional[Dict[str, Any]] = None
    is_frozen: bool = False
    source_type: Literal["local", "a2a"] = "local"
    a2a_config: Optional[A2AAgentDetailSchema] = None

    model_config = ConfigDict(from_attributes=True)


class CreateUpdateAgentSchema(BaseModel):
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
    memory_summarize_threshold: Optional[int] = 4000
    service_id: Optional[int] = None
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
    source_type: Literal["local", "a2a"] = "local"
    a2a_config: Optional[A2AAgentSourceConfigSchema] = None

    @model_validator(mode="after")
    def validate_source_config(self):
        if self.source_type == "a2a" and self.a2a_config is None:
            raise ValueError("a2a_config is required when source_type is 'a2a'")
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
    memory_summarize_threshold: Optional[int] = 4000
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


class CreateAgentRequestSchema(BaseModel):
    """Schema for creating a new agent via public API"""
    name: str
    description: Optional[str] = ""
    type: Literal["agent"] = "agent"
    is_tool: bool = False
    has_memory: bool = False
    memory_max_messages: Optional[int] = 20
    memory_max_tokens: Optional[int] = 4000
    memory_summarize_threshold: Optional[int] = 4000
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
    memory_summarize_threshold: Optional[int] = 4000
    service_id: Optional[int] = None
    vision_service_id: Optional[int] = None
    vision_system_prompt: Optional[str] = ""
    text_system_prompt: Optional[str] = ""
    output_parser_id: Optional[int] = None
    temperature: Optional[float] = DEFAULT_AGENT_TEMPERATURE
    tool_ids: Optional[List[int]] = []
    mcp_config_ids: Optional[List[int]] = []
    skill_ids: Optional[List[int]] = []


class UpdateAgentRequestSchema(BaseModel):
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
