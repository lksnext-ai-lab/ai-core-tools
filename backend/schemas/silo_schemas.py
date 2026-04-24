from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from schemas.embedding_service_schemas import EmbeddingServiceOptionSchema


class SiloListItemSchema(BaseModel):
    """Schema for silo list items"""
    silo_id: int
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    created_at: Optional[datetime] = None
    docs_count: int
    vector_db_type: Optional[str] = None
    is_frozen: bool = False

    model_config = ConfigDict(from_attributes=True)


class SiloDetailSchema(BaseModel):
    """Schema for detailed silo information"""
    silo_id: int
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    created_at: Optional[datetime] = None
    docs_count: int
    vector_db_type: Optional[str] = None
    # Current values for editing
    metadata_definition_id: Optional[int] = None
    embedding_service_id: Optional[int] = None
    # Form data
    output_parsers: List[Dict[str, Any]]
    embedding_services: List[EmbeddingServiceOptionSchema]
    vector_db_options: List[Dict[str, Any]] = []
    # Metadata definition fields for playground
    metadata_fields: Optional[List[Dict[str, Any]]] = None
    is_frozen: bool = False

    model_config = ConfigDict(from_attributes=True)


class CreateSiloSchema(BaseModel):
    """Schema for creating a new silo (vector_db_type is settable on creation only)"""
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    output_parser_id: Optional[int] = None
    embedding_service_id: Optional[int] = None
    vector_db_type: Optional[str] = None


class UpdateSiloSchema(BaseModel):
    """Schema for updating an existing silo (vector_db_type and embedding_service_id are immutable after creation)"""
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    output_parser_id: Optional[int] = None


# Kept for backward compatibility with the public API router
CreateUpdateSiloSchema = CreateSiloSchema


class SiloSearchSchema(BaseModel):
    """Schema for searching within a silo.

    `limit` controls the maximum number of results returned. When omitted or
    non-positive, the server applies `DEFAULT_SEARCH_LIMIT` (100). Values above
    `MAX_SEARCH_LIMIT` (200) are clamped server-side.
    """
    query: str
    limit: Optional[int] = None
    filter_metadata: Optional[Dict[str, Any]] = None
