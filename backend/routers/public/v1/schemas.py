from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

# ==================== BASE SCHEMAS ====================

class MessageResponseSchema(BaseModel):
    """Standard message response"""
    message: str

class CountResponseSchema(BaseModel):
    """Count response"""
    count: int

# ==================== AGENT CHAT SCHEMAS ====================

class ChatRequestSchema(BaseModel):
    """Chat request payload"""
    message: str
    attachments: Optional[List[Dict[str, Any]]] = None
    search_params: Optional[Dict[str, Any]] = None
    conversation_id: Optional[str] = None

class AgentResponseSchema(BaseModel):
    """Agent response - supports both string responses and structured JSON from output parsers"""
    response: Union[str, Dict[str, Any]]
    conversation_id: str
    usage: Optional[Dict[str, Any]] = None

# ==================== FILE OPERATION SCHEMAS ====================

class FileAttachmentSchema(BaseModel):
    """File attachment info"""
    file_reference: str
    filename: str
    size: int
    content_type: str

class AttachFileResponseSchema(BaseModel):
    """File attachment response"""
    file_reference: str
    message: str

class ListFilesResponseSchema(BaseModel):
    """List of attached files"""
    files: List[FileAttachmentSchema]

# ==================== OCR SCHEMAS ====================

class OCRResponseSchema(BaseModel):
    """OCR processing response"""
    text: str
    pages: int
    confidence: Optional[float] = None

# ==================== SILO SCHEMAS ====================

class SingleDocumentIndexSchema(BaseModel):
    """Schema for indexing a single document"""
    content: str
    metadata: Optional[Dict[str, Any]] = None

class MultipleDocumentIndexSchema(BaseModel):
    """Schema for indexing multiple documents"""
    documents: List[Dict[str, Any]]

class SiloSearchSchema(BaseModel):
    """Schema for searching in a silo"""
    query: str
    filter_metadata: Optional[Dict[str, Any]] = None

class DeleteDocsRequestSchema(BaseModel):
    """Schema for deleting documents"""
    ids: List[str]

class DocumentSchema(BaseModel):
    """Document schema"""
    page_content: str
    metadata: Dict[str, Any]

class DocsResponseSchema(BaseModel):
    """Documents response"""
    docs: List[DocumentSchema]

class FileIndexResponseSchema(BaseModel):
    """File indexing response"""
    message: str
    num_documents: int

# ==================== REPOSITORY SCHEMAS ====================

class RepositorySchema(BaseModel):
    """Repository schema"""
    model_config = ConfigDict(from_attributes=True)
    
    repository_id: int
    name: str
    app_id: int
    silo_id: Optional[int] = None
    create_date: Optional[datetime] = None

class CreateRepositoryRequestSchema(BaseModel):
    """Create repository request"""
    name: str

class RepositoryResponseSchema(BaseModel):
    """Single repository response"""
    repository: RepositorySchema

class RepositoriesResponseSchema(BaseModel):
    """Multiple repositories response"""
    repositories: List[RepositorySchema]

# ==================== RESOURCE SCHEMAS ====================

class ResourceSchema(BaseModel):
    """Resource schema"""
    model_config = ConfigDict(from_attributes=True)
    
    resource_id: int
    uri: str
    repository_id: int
    create_date: Optional[datetime] = None
    size: Optional[int] = None
    content_type: Optional[str] = None

class ResourceListResponseSchema(BaseModel):
    """List of resources"""
    resources: List[ResourceSchema]

class MultipleResourceResponseSchema(BaseModel):
    """Multiple resource creation response"""
    message: str
    created_resources: List[ResourceSchema]
    failed_files: List[str]

# ==================== COMMON PATH SCHEMAS ====================

class AppPathSchema(BaseModel):
    """App path parameter"""
    app_id: int

class AgentPathSchema(BaseModel):
    """Agent path parameters"""
    app_id: int
    agent_id: int

class SiloPathSchema(BaseModel):
    """Silo path parameters"""
    app_id: int
    silo_id: int

class RepoPathSchema(BaseModel):
    """Repository path parameters"""
    app_id: int
    repo_id: int

class ResourcePathSchema(BaseModel):
    """Resource path parameters"""
    app_id: int
    repo_id: int
    resource_id: int

class DetachFilePathSchema(BaseModel):
    """Detach file path parameters"""
    app_id: int
    agent_id: int
    file_reference: str 