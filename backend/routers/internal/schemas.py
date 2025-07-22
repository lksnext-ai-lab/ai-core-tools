from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

# ==================== APP SCHEMAS ====================

class AppListItemSchema(BaseModel):
    """Schema for app list items"""
    app_id: int
    name: str
    role: str  # "owner", "admin", "member"
    created_at: Optional[datetime]
    langsmith_configured: bool
    
    model_config = ConfigDict(from_attributes=True)


class AppDetailSchema(BaseModel):
    """Schema for detailed app information"""
    app_id: int
    name: str
    langsmith_api_key: str
    user_role: str
    created_at: Optional[datetime]
    owner_id: int
    
    model_config = ConfigDict(from_attributes=True)


class CreateAppSchema(BaseModel):
    """Schema for creating a new app"""
    name: str
    langsmith_api_key: Optional[str] = ""


class UpdateAppSchema(BaseModel):
    """Schema for updating an app"""
    name: str
    langsmith_api_key: Optional[str] = ""


# ==================== AGENT SCHEMAS ====================

class AgentListItemSchema(BaseModel):
    """Schema for agent list items"""
    agent_id: int
    name: str
    type: str  # "agent", "ocr_agent", etc.
    is_tool: bool
    created_at: Optional[datetime]
    request_count: int
    
    model_config = ConfigDict(from_attributes=True)


class AgentDetailSchema(BaseModel):
    """Schema for detailed agent information"""
    agent_id: int
    name: str
    system_prompt: str
    prompt_template: str
    type: str
    is_tool: bool
    created_at: Optional[datetime]
    request_count: int
    # Form data for editing
    ai_services: List[Dict[str, Any]]
    silos: List[Dict[str, Any]]
    output_parsers: List[Dict[str, Any]]
    tools: List[Dict[str, Any]]
    mcp_configs: List[Dict[str, Any]]
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateAgentSchema(BaseModel):
    """Schema for creating or updating an agent"""
    name: str
    system_prompt: Optional[str] = ""
    prompt_template: Optional[str] = ""
    type: str = "agent"  # "agent", "ocr_agent"
    is_tool: bool = False
    tool_ids: Optional[List[int]] = []
    mcp_config_ids: Optional[List[int]] = []


class UpdatePromptSchema(BaseModel):
    """Schema for updating agent prompts"""
    type: str  # "system" or "template"
    prompt: str


# ==================== REPOSITORY SCHEMAS ====================

class RepositoryListItemSchema(BaseModel):
    """Schema for repository list items"""
    repository_id: int
    name: str
    created_at: Optional[datetime]
    resource_count: int
    
    model_config = ConfigDict(from_attributes=True)


class RepositoryDetailSchema(BaseModel):
    """Schema for detailed repository information"""
    repository_id: int
    name: str
    created_at: Optional[datetime]
    resources: List[Dict[str, Any]]
    embedding_services: List[Dict[str, Any]]
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateRepositorySchema(BaseModel):
    """Schema for creating or updating a repository"""
    name: str


# ==================== RESOURCE SCHEMAS ====================

class ResourceListItemSchema(BaseModel):
    """Schema for resource list items"""
    resource_id: int
    name: str
    file_type: str
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


# ==================== API KEY SCHEMAS ====================

class APIKeyListItemSchema(BaseModel):
    """Schema for API key list items"""
    key_id: int
    name: str
    is_active: bool
    created_at: Optional[datetime]
    last_used_at: Optional[datetime]
    key_preview: str  # First 8 chars + "..."
    
    model_config = ConfigDict(from_attributes=True)


class APIKeyDetailSchema(BaseModel):
    """Schema for detailed API key information"""
    key_id: int
    name: str
    is_active: bool
    created_at: Optional[datetime]
    last_used_at: Optional[datetime]
    key_preview: str
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateAPIKeySchema(BaseModel):
    """Schema for creating or updating an API key"""
    name: str
    is_active: Optional[bool] = True


class APIKeyCreateResponseSchema(APIKeyDetailSchema):
    """Schema for API key creation response - includes actual key value once"""
    key_value: Optional[str] = None  # Only returned on creation
    message: str


# ==================== SILO SCHEMAS ====================

class SiloListItemSchema(BaseModel):
    """Schema for silo list items"""
    silo_id: int
    name: str
    type: Optional[str]
    created_at: Optional[datetime]
    docs_count: int
    
    model_config = ConfigDict(from_attributes=True)


class SiloDetailSchema(BaseModel):
    """Schema for detailed silo information"""
    silo_id: int
    name: str
    type: Optional[str]
    created_at: Optional[datetime]
    docs_count: int
    output_parsers: List[Dict[str, Any]]
    embedding_services: List[Dict[str, Any]]
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateSiloSchema(BaseModel):
    """Schema for creating or updating a silo"""
    name: str
    type: Optional[str] = None
    output_parser_id: Optional[int] = None
    embedding_service_id: Optional[int] = None


class SiloSearchSchema(BaseModel):
    """Schema for searching within a silo"""
    query: str
    limit: Optional[int] = 10


# ==================== AI SERVICE SCHEMAS ====================

class AIServiceListItemSchema(BaseModel):
    """Schema for AI service list items"""
    service_id: int
    name: str
    provider: Optional[str]
    model_name: str
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class AIServiceDetailSchema(BaseModel):
    """Schema for detailed AI service information"""
    service_id: int
    name: str
    provider: Optional[str]
    model_name: str
    api_key: str
    base_url: str
    created_at: Optional[datetime]
    available_providers: List[Dict[str, Any]]
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateAIServiceSchema(BaseModel):
    """Schema for creating or updating an AI service"""
    name: str
    provider: str
    model_name: str
    api_key: str
    base_url: Optional[str] = ""


# ==================== EMBEDDING SERVICE SCHEMAS ====================

class EmbeddingServiceListItemSchema(BaseModel):
    """Schema for embedding service list items"""
    service_id: int
    name: str
    provider: Optional[str]
    model_name: str
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class EmbeddingServiceDetailSchema(BaseModel):
    """Schema for detailed embedding service information"""
    service_id: int
    name: str
    provider: Optional[str]
    model_name: str
    api_key: str
    base_url: str
    created_at: Optional[datetime]
    available_providers: List[Dict[str, Any]]
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateEmbeddingServiceSchema(BaseModel):
    """Schema for creating or updating an embedding service"""
    name: str
    provider: str
    model_name: str
    api_key: str
    base_url: Optional[str] = ""


# ==================== OUTPUT PARSER SCHEMAS ====================

class OutputParserListItemSchema(BaseModel):
    """Schema for output parser list items"""
    parser_id: int
    name: str
    type: str
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class OutputParserDetailSchema(BaseModel):
    """Schema for detailed output parser information"""
    parser_id: int
    name: str
    type: str
    instructions: str
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateOutputParserSchema(BaseModel):
    """Schema for creating or updating an output parser"""
    name: str
    type: str = "json"
    instructions: str = ""


# ==================== MCP CONFIG SCHEMAS ====================

class MCPConfigListItemSchema(BaseModel):
    """Schema for MCP config list items"""
    config_id: int
    name: str
    transport_type: Optional[str]
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class MCPConfigDetailSchema(BaseModel):
    """Schema for detailed MCP config information"""
    config_id: int
    name: str
    transport_type: Optional[str]
    command: str
    args: str
    env: str
    created_at: Optional[datetime]
    available_transport_types: List[Dict[str, Any]]
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateMCPConfigSchema(BaseModel):
    """Schema for creating or updating an MCP config"""
    name: str
    transport_type: str
    command: str = ""
    args: str = ""
    env: str = ""


# ==================== COMMON RESPONSE SCHEMAS ====================

class MessageResponseSchema(BaseModel):
    """Standard message response"""
    message: str


class ErrorResponseSchema(BaseModel):
    """Standard error response"""
    detail: str 