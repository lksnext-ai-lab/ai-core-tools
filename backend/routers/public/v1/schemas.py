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

# Note: Chat endpoint now uses Form data instead of JSON body for multipart/form-data support
# Parameters: message, files, file_references, search_params, conversation_id

class AgentResponseSchema(BaseModel):
    """Agent response - supports both string responses and structured JSON from output parsers"""
    response: Union[str, Dict[str, Any]]
    conversation_id: Optional[int] = None
    usage: Optional[Dict[str, Any]] = None

# ==================== FILE OPERATION SCHEMAS ====================

class FileAttachmentSchema(BaseModel):
    """File attachment info with visual feedback data"""
    file_id: str
    filename: str
    file_type: str
    uploaded_at: Optional[str] = None
    # Visual feedback fields
    file_size_bytes: Optional[int] = None
    file_size_display: Optional[str] = None  # Human readable size (e.g., "2.5 MB")
    processing_status: Optional[str] = None  # "uploaded", "processing", "ready", "error"
    content_preview: Optional[str] = None  # First 200 chars of extracted content
    has_extractable_content: Optional[bool] = None  # True if text was extracted
    mime_type: Optional[str] = None
    conversation_id: Optional[str] = None  # Associated conversation if any

class AttachFileResponseSchema(BaseModel):
    """File attachment response with visual feedback data"""
    success: bool
    file_id: str
    filename: str
    file_type: str
    message: str
    # Conversation context (for memory-enabled agents)
    conversation_id: Optional[str] = None  # ID of the conversation the file is attached to
    # Visual feedback fields
    file_size_bytes: Optional[int] = None
    file_size_display: Optional[str] = None  # Human readable size (e.g., "2.5 MB")
    processing_status: str = "ready"  # "uploaded", "processing", "ready", "error"
    content_preview: Optional[str] = None  # First 200 chars of extracted content
    has_extractable_content: bool = False  # True if text was extracted
    mime_type: Optional[str] = None

class ListFilesResponseSchema(BaseModel):
    """List of attached files"""
    files: List[FileAttachmentSchema]
    total_size_bytes: Optional[int] = None
    total_size_display: Optional[str] = None

class DetachFileResponseSchema(BaseModel):
    """File detachment response"""
    success: bool
    message: str

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

class DeleteByMetadataRequestSchema(BaseModel):
    """Schema for deleting documents by metadata filter"""
    filter_metadata: Dict[str, Any]

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