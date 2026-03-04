from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from models.agent import DEFAULT_AGENT_TEMPERATURE

# ==================== AGENT SCHEMAS ====================

class AgentListItemSchema(BaseModel):
    """Schema for agent list items"""
    agent_id: int
    name: str
    description: Optional[str] = None
    type: str  # "agent", "ocr_agent", etc.
    is_tool: bool
    created_at: Optional[datetime]
    request_count: int
    service_id: Optional[int] = None
    ai_service: Optional[Dict[str, Any]] = None  # AI service details
    marketplace_visibility: Optional[str] = None
    
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
    created_at: Optional[datetime]
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
    type: str = "agent"  # "agent" or "ocr_agent"
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
