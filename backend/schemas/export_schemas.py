"""Export schemas for all component types.

These schemas define the structure of exported data with:
- Name-based references (not database IDs)
- Secrets sanitized (api_key = None)
- Heavy data excluded (vectors, files, conversations, crawled content)
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

from schemas.agent_schemas import A2AAgentFieldsMixin


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
    type: str  # 'str', 'int', 'float', 'bool', 'date', 'list', 'dict', 'parser'
    description: str
    optional: bool = False  # If True, the field is optional (may be absent in LLM output)
    parser_name: Optional[str] = None  # For type='parser' (name-based reference)
    list_item_type: Optional[str] = None  # For type='list'
    list_item_parser_name: Optional[str] = None  # For list of parsers (name-based reference)


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


class ExportDomainUrlSchema(BaseModel):
    """Domain URL export schema"""

    url: str
    # Exclude: crawled content, status (transient)


class ExportDomainSchema(BaseModel):
    """Domain export schema (structure and URLs only)"""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    base_url: str
    content_tag: Optional[str] = None
    content_class: Optional[str] = None
    content_id: Optional[str] = None
    silo_name: Optional[str] = None  # Reference by name
    urls: List[ExportDomainUrlSchema] = []
    # Exclude: crawled content (heavy data)


# ==================== REPOSITORY ====================


class ExportRepositorySchema(BaseModel):
    """Repository export schema (structure only)"""

    name: str = Field(..., min_length=1, max_length=255)
    type: str
    silo_name: Optional[str] = None  # Reference by name
    # Exclude: resources, files (heavy data)


# ==================== MIDDLEWARE ====================


class ExportMiddlewareSchema(BaseModel):
    """Middleware export schema.

    The AI service a config may reference (summarization model, PII detector) travels by
    name in ``ai_service_name``; inside ``config`` it is exported as ``agent_llm``.
    """

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    middleware_type: str
    config: Dict[str, Any] = {}
    ai_service_name: Optional[str] = None


# ==================== AGENT ====================


class ExportAgentToolRefSchema(BaseModel):
    """Agent-to-Agent tool reference"""

    tool_agent_name: str  # Reference by name


class ExportAgentMCPRefSchema(BaseModel):
    """Agent-to-MCP reference"""

    mcp_name: str  # Reference by name


class ExportAgentSchema(A2AAgentFieldsMixin):
    """Agent export schema (configuration only, no conversations).

    Inherits the A2A (Agent2Agent protocol) fields and their validators from
    ``A2AAgentFieldsMixin`` (step_009) so export/import reuse the exact same caps
    and normalization instead of duplicating them (FR-24, AC-39). Import always
    forces ``a2a_enabled=False`` regardless of the exported value (enforced in
    ``AgentImportService``, never here, so a round-trip export/import of the same
    file still faithfully reports what was in the file).
    """

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    prompt_template: Optional[str] = None
    service_name: Optional[str] = None  # Reference by name
    silo_name: Optional[str] = None  # Reference by name
    output_parser_name: Optional[str] = None  # Reference by name
    agent_tool_refs: List[ExportAgentToolRefSchema] = []
    agent_mcp_refs: List[ExportAgentMCPRefSchema] = []
    middleware_names: List[str] = []  # Execution order; definitions travel alongside
    is_tool: Optional[bool] = False  # Can be used as a tool by other agents
    has_memory: Optional[bool] = False
    skill_router_enabled: Optional[bool] = False
    memory_max_messages: Optional[int] = 20
    memory_max_tokens: Optional[int] = None
    memory_summarize_threshold: Optional[int] = 10
    temperature: Optional[float] = 0.7
    # OCR-specific fields
    vision_service_name: Optional[str] = None  # Reference by name (OCR agents only)
    vision_system_prompt: Optional[str] = None  # OCR agents only
    text_system_prompt: Optional[str] = None  # OCR agents only
    # Exclude: conversation history, request_count, usage stats


# ==================== APP ====================


class ExportAppSchema(BaseModel):
    """App metadata export schema"""

    name: str = Field(..., min_length=1, max_length=255)
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
    embedding_service: Optional[ExportEmbeddingServiceSchema] = None
    output_parser: Optional[ExportOutputParserSchema] = None


class DomainExportFileSchema(BaseModel):
    """Domain export file"""

    metadata: ExportMetadataSchema
    domain: ExportDomainSchema
    silo: Optional[ExportSiloSchema] = None
    embedding_service: Optional[ExportEmbeddingServiceSchema] = None
    output_parser: Optional[ExportOutputParserSchema] = None


class MiddlewareExportFileSchema(BaseModel):
    """Middleware export file"""

    metadata: ExportMetadataSchema
    middleware: ExportMiddlewareSchema


class AgentExportFileSchema(BaseModel):
    """Agent export file with dependencies"""

    metadata: ExportMetadataSchema
    agent: ExportAgentSchema
    ai_service: Optional[ExportAIServiceSchema] = None
    silo: Optional[ExportSiloSchema] = None
    silo_embedding_service: Optional[ExportEmbeddingServiceSchema] = None  # Silo's embedding service (separate from agent's ai_service)
    silo_output_parser: Optional[ExportOutputParserSchema] = None  # Silo's metadata definition (may differ from agent's parser)
    output_parser: Optional[ExportOutputParserSchema] = None
    mcp_configs: List[ExportMCPConfigSchema] = []
    middlewares: List[ExportMiddlewareSchema] = []  # The agent's middlewares
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
    domains: List[ExportDomainSchema] = []
    middlewares: List[ExportMiddlewareSchema] = []
    agents: List[ExportAgentSchema] = []
