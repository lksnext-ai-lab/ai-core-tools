from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== EMBEDDING SERVICE SCHEMAS ====================

class EmbeddingServiceListItemSchema(BaseModel):
    """Schema for embedding service list items"""
    service_id: int
    name: str
    provider: Optional[str]
    model_name: str
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class EmbeddingServiceDetailSchema(BaseModel):
    """Schema for detailed embedding service information"""
    service_id: int
    name: str
    provider: Optional[str]
    model_name: str
    api_key: str
    base_url: str
    created_at: Optional[datetime]
    available_providers: List[Dict[str, Any]]
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateEmbeddingServiceSchema(BaseModel):
    """Schema for creating or updating an embedding service"""
    name: str
    provider: str
    model_name: str
    api_key: str
    base_url: Optional[str] = ""
