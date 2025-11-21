from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class SiloListItemSchema(BaseModel):
    """Schema for silo list items"""
    silo_id: int
    name: str
    description: Optional[str] = None
    type: Optional[str]
    created_at: Optional[datetime]
    docs_count: int
    vector_db_type: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class SiloDetailSchema(BaseModel):
    """Schema for detailed silo information"""
    silo_id: int
    name: str
    description: Optional[str] = None
    type: Optional[str]
    created_at: Optional[datetime]
    docs_count: int
    vector_db_type: Optional[str] = None
    # Current values for editing
    metadata_definition_id: Optional[int] = None
    embedding_service_id: Optional[int] = None
    # Form data
    output_parsers: List[Dict[str, Any]]
    embedding_services: List[Dict[str, Any]]
    vector_db_options: List[Dict[str, Any]] = []
    # Metadata definition fields for playground
    metadata_fields: Optional[List[Dict[str, Any]]] = None
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateSiloSchema(BaseModel):
    """Schema for creating or updating a silo"""
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    output_parser_id: Optional[int] = None
    embedding_service_id: Optional[int] = None
    vector_db_type: Optional[str] = None


class SiloSearchSchema(BaseModel):
    """Schema for searching within a silo"""
    query: str
    limit: Optional[int] = 10
    filter_metadata: Optional[Dict[str, Any]] = None
