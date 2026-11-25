from schemas.service_lifecycle_schemas import ServiceLifecycleWarningSchema
from schemas.indexing_schemas import IndexingOptionsSchema, IndexingSettingsInput
from schemas.media_schemas import MediaResponse
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class MetadataFieldSchema(BaseModel):
    """Schema for metadata field information"""
    name: str
    type: str
    description: str


class RepositoryListItemSchema(BaseModel):
    """Schema for repository list items"""
    repository_id: int
    name: str
    type: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    resource_count: int
    vector_db_type: Optional[str] = None
    lifecycle_warnings: List[ServiceLifecycleWarningSchema] = []
    
    model_config = ConfigDict(from_attributes=True)


class RepositoryDetailSchema(BaseModel):
    """Schema for detailed repository information"""
    repository_id: int
    name: str
    type: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    resources: List[Dict[str, Any]]
    folders: List[Dict[str, Any]] = []
    embedding_services: List[Dict[str, Any]]
    embedding_service_id: Optional[int] = None
    silo_id: Optional[int] = None
    vector_db_type: Optional[str] = None
    vector_db_options: List[Dict[str, Any]] = []
    metadata_fields: Optional[List[MetadataFieldSchema]] = []
    media: List[MediaResponse] = []
    ai_services: List[Dict[str, Any]] = []
    transcription_service_id: Optional[int] = None
    video_ai_service_id: Optional[int] = None
    # Indexing settings of the repository's silo and what the form can choose from
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    pdf_loader: Optional[str] = None
    pdf_loader_options: Dict[str, Any] = {}
    indexing_options: Optional[IndexingOptionsSchema] = None
    # Recorded failures of the services the repository's silo uses (e.g. a revoked API key)
    service_warnings: List[str] = []
    lifecycle_warnings: List[ServiceLifecycleWarningSchema] = []
    
    model_config = ConfigDict(from_attributes=True)


class CreateRepositorySchema(IndexingSettingsInput):
    """Schema for creating a new repository (vector_db_type is settable on creation only)"""
    name: str
    type: Optional[str] = None
    status: Optional[str] = None
    embedding_service_id: Optional[int] = None
    vector_db_type: Optional[str] = None
    transcription_service_id: Optional[int] = None
    video_ai_service_id: Optional[int] = None


class UpdateRepositorySchema(IndexingSettingsInput):
    """Schema for updating an existing repository (vector_db_type is immutable after creation)"""
    name: str
    type: Optional[str] = None
    status: Optional[str] = None
    embedding_service_id: Optional[int] = None
    transcription_service_id: Optional[int] = None
    video_ai_service_id: Optional[int] = None


# Backward-compatible alias used by internal callers that haven't been updated yet
CreateUpdateRepositorySchema = CreateRepositorySchema


class RepositorySearchSchema(BaseModel):
    """Schema for searching within a repository"""
    query: str
    limit: Optional[int] = 10
    filter_metadata: Optional[Dict[str, Any]] = None
