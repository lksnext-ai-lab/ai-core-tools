from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime

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
    vector_db_type: Optional[str] = None
    
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
    vector_db_type: Optional[str] = None
    
    # Form data for editing
    embedding_services: List[Dict[str, Any]] = []
    embedding_service_id: Optional[int] = None
    vector_db_options: List[Dict[str, Any]] = []
    
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
    vector_db_type: Optional[str] = None


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
