"""Export schemas for all component types.

These schemas define the structure of exported data with:
- Name-based references (not database IDs)
- Secrets sanitized (api_key = None)
- Heavy data excluded (vectors, files, conversations, crawled content)
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== METADATA ====================


class ExportMetadataSchema(BaseModel):
    """Common metadata for all exports"""

    export_version: str = Field(default="1.0.0")
    export_date: datetime = Field(default_factory=datetime.now)
    exported_by: Optional[str] = None
    source_app_id: Optional[int] = None


# ==================== AI SERVICE ====================


class ExportAIServiceSchema(BaseModel):
    """AI Service export schema"""

    name: str = Field(..., min_length=1, max_length=255)
    api_key: Optional[str] = None  # Always None (security)
    provider: str
    model_name: str
    endpoint: Optional[str] = None
    description: Optional[str] = None
    api_version: Optional[str] = None


# ==================== EMBEDDING SERVICE ====================


class ExportEmbeddingServiceSchema(BaseModel):
    """Embedding Service export schema"""

    name: str = Field(..., min_length=1, max_length=255)
    api_key: Optional[str] = None  # Always None (security)
    provider: str
    model_name: str
    endpoint: Optional[str] = None
    description: Optional[str] = None
    api_version: Optional[str] = None


# ==================== OUTPUT PARSER ====================


class ExportOutputParserFieldSchema(BaseModel):
    """Output Parser field export schema"""

    name: str
    type: str  # 'str', 'int', 'float', 'bool', 'date', 'list', 'parser'
    description: str
    parser_id: Optional[int] = None  # For type='parser'
    list_item_type: Optional[str] = None  # For type='list'
    list_item_parser_id: Optional[int] = None  # For list of parsers


class ExportOutputParserSchema(BaseModel):
    """Output Parser export schema"""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    fields: List[ExportOutputParserFieldSchema] = []


# ==================== MCP CONFIG ====================


class ExportMCPConfigSchema(BaseModel):
    """MCP Configuration export schema (sanitized)"""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    config: Optional[str] = None  # JSON string (sanitized - no auth tokens)


# ==================== SILO ====================


class ExportSiloSchema(BaseModel):
    """Silo export schema (structure only)"""

    name: str = Field(..., min_length=1, max_length=255)
    type: str
    vector_db_type: Optional[str] = "UNKNOWN"  # Default for silos without configured vector DB
    embedding_service_name: Optional[str] = None  # Reference by name
    metadata_definition_name: Optional[str] = None  # Reference to OutputParser
    fixed_metadata: bool = False
    description: Optional[str] = None
    # Exclude: vectors, embeddings (heavy data), collection_name (auto-generated)


# ==================== DOMAIN ====================


class ExportDomainSchema(BaseModel):
    """Domain export schema (URLs only)"""

    domain_url: str
    # Exclude: crawled content


# ==================== REPOSITORY ====================


class ExportRepositorySchema(BaseModel):
    """Repository export schema (structure only)"""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    repo_type: str
    silo_name: Optional[str] = None  # Reference by name
    domains: List[ExportDomainSchema] = []
    # Exclude: resources, files (heavy data)


# ==================== AGENT ====================


class ExportAgentToolRefSchema(BaseModel):
    """Agent-to-Agent tool reference"""

    tool_agent_name: str  # Reference by name


class ExportAgentMCPRefSchema(BaseModel):
    """Agent-to-MCP reference"""

    mcp_name: str  # Reference by name


class ExportAgentSchema(BaseModel):
    """Agent export schema"""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    service_name: Optional[str] = None  # Reference by name
    silo_name: Optional[str] = None  # Reference by name
    output_parser_name: Optional[str] = None  # Reference by name
    agent_tool_refs: List[ExportAgentToolRefSchema] = []
    agent_mcp_refs: List[ExportAgentMCPRefSchema] = []
    memory_type: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    model_name: Optional[str] = None
    # Exclude: conversation history


# ==================== APP ====================


class ExportAppSchema(BaseModel):
    """App metadata export schema"""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    agent_rate_limit: Optional[int] = None
    enable_langsmith: bool = False


# ==================== COMPONENT-SPECIFIC EXPORT FILE SCHEMAS ====================


class AIServiceExportFileSchema(BaseModel):
    """AI Service export file"""

    metadata: ExportMetadataSchema
    ai_service: ExportAIServiceSchema


class EmbeddingServiceExportFileSchema(BaseModel):
    """Embedding Service export file"""

    metadata: ExportMetadataSchema
    embedding_service: ExportEmbeddingServiceSchema


class OutputParserExportFileSchema(BaseModel):
    """Output Parser export file"""

    metadata: ExportMetadataSchema
    output_parser: ExportOutputParserSchema


class MCPConfigExportFileSchema(BaseModel):
    """MCP Config export file"""

    metadata: ExportMetadataSchema
    mcp_config: ExportMCPConfigSchema


class SiloExportFileSchema(BaseModel):
    """Silo export file"""

    metadata: ExportMetadataSchema
    silo: ExportSiloSchema
    embedding_service: Optional[ExportEmbeddingServiceSchema] = None
    output_parser: Optional[ExportOutputParserSchema] = None


class RepositoryExportFileSchema(BaseModel):
    """Repository export file"""

    metadata: ExportMetadataSchema
    repository: ExportRepositorySchema
    silo: Optional[ExportSiloSchema] = None


class AgentExportFileSchema(BaseModel):
    """Agent export file with dependencies"""

    metadata: ExportMetadataSchema
    agent: ExportAgentSchema
    ai_service: Optional[ExportAIServiceSchema] = None
    silo: Optional[ExportSiloSchema] = None
    output_parser: Optional[ExportOutputParserSchema] = None
    mcp_configs: List[ExportMCPConfigSchema] = []
    agent_tools: List[ExportAgentSchema] = []  # Referenced agents


# ==================== FULL APP EXPORT ====================


class AppExportFileSchema(BaseModel):
    """Complete app export file"""

    metadata: ExportMetadataSchema
    app: ExportAppSchema
    ai_services: List[ExportAIServiceSchema] = []
    embedding_services: List[ExportEmbeddingServiceSchema] = []
    output_parsers: List[ExportOutputParserSchema] = []
    mcp_configs: List[ExportMCPConfigSchema] = []
    silos: List[ExportSiloSchema] = []
    repositories: List[ExportRepositorySchema] = []
    agents: List[ExportAgentSchema] = []
