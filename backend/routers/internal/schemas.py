from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime

# ==================== AGENT SCHEMAS ====================

class AgentListItemSchema(BaseModel):
    """Schema for agent list items"""
    agent_id: int
    name: str
    type: str  # "agent", "ocr_agent", etc.
    is_tool: bool
    created_at: Optional[datetime]
    request_count: int
    service_id: Optional[int] = None
    ai_service: Optional[Dict[str, Any]] = None  # AI service details
    
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
    service_id: Optional[int] = None
    silo_id: Optional[int] = None
    output_parser_id: Optional[int] = None
    tool_ids: List[int] = []
    mcp_config_ids: List[int] = []
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
    service_id: Optional[int] = None
    silo_id: Optional[int] = None
    output_parser_id: Optional[int] = None
    tool_ids: Optional[List[int]] = []
    mcp_config_ids: Optional[List[int]] = []
    # OCR-specific fields
    vision_service_id: Optional[int] = None
    vision_system_prompt: Optional[str] = None
    text_system_prompt: Optional[str] = None


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
    embedding_service_id: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateRepositorySchema(BaseModel):
    """Schema for creating or updating a repository"""
    name: str
    embedding_service_id: Optional[int] = None


# ==================== RESOURCE SCHEMAS ====================

class ResourceListItemSchema(BaseModel):
    """Schema for resource list items"""
    resource_id: int
    name: str
    file_type: str
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


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
    # Current values for editing
    metadata_definition_id: Optional[int] = None
    embedding_service_id: Optional[int] = None
    # Form data
    output_parsers: List[Dict[str, Any]]
    embedding_services: List[Dict[str, Any]]
    # Metadata definition fields for playground
    metadata_fields: Optional[List[Dict[str, Any]]] = None
    
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
    filter_metadata: Optional[Dict[str, Any]] = None


# ==================== OUTPUT PARSER SCHEMAS ====================

class OutputParserListItemSchema(BaseModel):
    """Schema for output parser list items"""
    parser_id: int
    name: str
    description: Optional[str]
    field_count: int  # Number of fields in the parser
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class OutputParserFieldSchema(BaseModel):
    """Schema for individual parser fields"""
    name: str
    type: str  # 'str', 'int', 'float', 'bool', 'date', 'list', 'parser'
    description: str
    parser_id: Optional[int] = None  # For type='parser'
    list_item_type: Optional[str] = None  # For type='list'
    list_item_parser_id: Optional[int] = None  # For list of parsers


class OutputParserDetailSchema(BaseModel):
    """Schema for detailed output parser information"""
    parser_id: int
    name: str
    description: Optional[str]
    fields: List[OutputParserFieldSchema]
    created_at: Optional[datetime]
    available_parsers: List[Dict[str, Any]]  # Other parsers for references
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateOutputParserSchema(BaseModel):
    """Schema for creating or updating an output parser"""
    name: str
    description: Optional[str] = ""
    fields: List[OutputParserFieldSchema]


# ==================== DOMAIN SCHEMAS ====================

class DomainListItemSchema(BaseModel):
    """Schema for domain list items"""
    domain_id: int
    name: str
    description: str
    base_url: str
    created_at: Optional[datetime]
    url_count: int = 0
    silo_id: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


class DomainDetailSchema(BaseModel):
    """Schema for detailed domain information"""
    domain_id: int
    name: str
    description: str
    base_url: str
    content_tag: str
    content_class: str
    content_id: str
    created_at: Optional[datetime]
    silo_id: Optional[int] = None
    url_count: int = 0
    
    # Form data for editing
    embedding_services: List[Dict[str, Any]] = []
    embedding_service_id: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateDomainSchema(BaseModel):
    """Schema for creating or updating a domain"""
    name: str
    description: Optional[str] = ""
    base_url: str
    content_tag: Optional[str] = "body"
    content_class: Optional[str] = ""
    content_id: Optional[str] = ""
    embedding_service_id: Optional[int] = None


# ==================== URL SCHEMAS ====================

class URLListItemSchema(BaseModel):
    """Schema for URL list items"""
    url_id: int
    url: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime] = None
    status: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class URLDetailSchema(BaseModel):
    """Schema for detailed URL information"""
    url_id: int
    url: str
    domain_id: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime] = None
    status: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class CreateURLSchema(BaseModel):
    """Schema for creating a new URL"""
    url: str
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        if not v or not v.strip():
            raise ValueError('URL cannot be empty')
        return v.strip()


class URLActionResponseSchema(BaseModel):
    """Schema for URL action responses"""
    success: bool
    message: str
    url_id: Optional[int] = None 