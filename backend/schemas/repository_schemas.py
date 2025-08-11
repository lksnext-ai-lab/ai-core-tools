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
    silo_id: Optional[int] = None
    metadata_fields: Optional[List[MetadataFieldSchema]] = []
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateRepositorySchema(BaseModel):
    """Schema for creating or updating a repository"""
    name: str
    embedding_service_id: Optional[int] = None


class RepositorySearchSchema(BaseModel):
    """Schema for searching within a repository"""
    query: str
    limit: Optional[int] = 10
    filter_metadata: Optional[Dict[str, Any]] = None
