from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class ResourceListItemSchema(BaseModel):
    """Schema for resource list items"""
    resource_id: int
    name: str
    file_type: str
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)
