from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== MCP CONFIG SCHEMAS ====================

class MCPConfigListItemSchema(BaseModel):
    """Schema for MCP config list items"""
    config_id: int
    name: str
    description: Optional[str] = ""
    created_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class MCPConfigDetailSchema(BaseModel):
    """Schema for detailed MCP config information"""
    config_id: int
    name: str
    description: Optional[str] = ""
    config: str  # JSON string containing the full MCP server configuration
    ssl_verify: bool = True
    created_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateMCPConfigSchema(BaseModel):
    """Schema for creating or updating an MCP config"""
    name: str
    description: Optional[str] = ""
    config: str  # JSON string containing the full MCP server configuration
    ssl_verify: bool = True

    @field_validator("config", mode="before")
    @classmethod
    def _strip_config_envelope(cls, v):
        # Trim whitespace at both ends only — preserves the JSON structure
        # but cleans up trailing newlines from copy-paste of multi-line configs.
        # Inner credentials embedded in the JSON keep their original form.
        return v.strip() if isinstance(v, str) else v
