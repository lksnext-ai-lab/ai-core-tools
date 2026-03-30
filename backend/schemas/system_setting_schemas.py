from pydantic import BaseModel, ConfigDict
from typing import Optional, Any
from datetime import datetime


class SystemSettingRead(BaseModel):
    """Schema for reading system settings with resolved values"""
    key: str
    value: Optional[str] = None  # Raw value from DB (null means "use default")
    type: str
    category: str
    description: Optional[str] = None
    updated_at: Optional[datetime] = None
    resolved_value: Any  # The actual typed value after resolution
    source: str  # One of: "env", "db", "default"
    
    model_config = ConfigDict(from_attributes=True)


class SystemSettingUpdate(BaseModel):
    """Schema for updating a system setting value"""
    value: str  # New value to set (as string, will be type-casted based on setting.type)
