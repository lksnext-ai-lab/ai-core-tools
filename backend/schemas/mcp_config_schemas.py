from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== MCP CONFIG SCHEMAS ====================

class MCPConfigListItemSchema(BaseModel):
    """Schema for MCP config list items"""
    config_id: int
    name: str
    transport_type: Optional[str]
    created_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class MCPConfigDetailSchema(BaseModel):
    """Schema for detailed MCP config information"""
    config_id: int
    name: str
    server_name: str
    description: Optional[str]
    transport_type: Optional[str]
    command: str
    args: str
    env: str
    created_at: Optional[datetime]
    available_transport_types: List[Dict[str, Any]]
    
    model_config = ConfigDict(from_attributes=True)


class CreateUpdateMCPConfigSchema(BaseModel):
    """Schema for creating or updating an MCP config"""
    name: str
    server_name: str
    description: Optional[str] = ""
    transport_type: str
    command: str = ""
    args: str = ""
    env: str = ""
