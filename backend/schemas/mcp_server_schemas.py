from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== MCP SERVER SCHEMAS ====================

class MCPServerAgentSchema(BaseModel):
    """Schema for an agent associated with an MCP server"""
    agent_id: int
    agent_name: str
    agent_description: Optional[str] = None
    tool_name_override: Optional[str] = None
    tool_description_override: Optional[str] = None
    is_available: bool = True  # Whether the agent is still valid (exists and is_tool=True)
    unavailable_reason: Optional[str] = None  # Reason if not available

    model_config = ConfigDict(from_attributes=True)


class MCPServerAgentInputSchema(BaseModel):
    """Schema for adding/updating an agent in an MCP server"""
    agent_id: int
    tool_name_override: Optional[str] = None
    tool_description_override: Optional[str] = None


class MCPConnectionHintsSchema(BaseModel):
    """Schema for MCP connection configuration hints"""
    claude_desktop: Dict[str, Any]
    cursor: Dict[str, Any]
    curl_example: str
    endpoint_url: str
    endpoint_url_by_id: str


class MCPServerListSchema(BaseModel):
    """Schema for MCP server list items"""
    server_id: int
    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool
    agent_count: int
    endpoint_url: str
    create_date: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MCPServerDetailSchema(BaseModel):
    """Schema for detailed MCP server information"""
    server_id: int
    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool
    rate_limit: int
    agents: List[MCPServerAgentSchema]
    endpoint_url: str
    endpoint_url_by_id: str
    connection_hints: MCPConnectionHintsSchema
    create_date: Optional[datetime] = None
    update_date: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CreateMCPServerSchema(BaseModel):
    """Schema for creating a new MCP server"""
    name: str = Field(..., min_length=1, max_length=100)
    slug: Optional[str] = Field(None, max_length=100)  # Auto-generated if not provided
    description: Optional[str] = Field("", max_length=1000)
    is_active: bool = True
    rate_limit: int = Field(0, ge=0)  # 0 = unlimited
    agent_ids: List[int] = []


class UpdateMCPServerSchema(BaseModel):
    """Schema for updating an MCP server"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None
    rate_limit: Optional[int] = Field(None, ge=0)
    agent_ids: Optional[List[int]] = None


class UpdateMCPServerAgentsSchema(BaseModel):
    """Schema for updating the agents in an MCP server"""
    agents: List[MCPServerAgentInputSchema]


# ==================== APP SLUG SCHEMAS ====================

class UpdateAppSlugSchema(BaseModel):
    """Schema for updating an app's slug"""
    slug: str = Field(..., min_length=1, max_length=100, pattern=r'^[a-z0-9-]+$')


class AppSlugResponseSchema(BaseModel):
    """Schema for app slug response"""
    app_id: int
    slug: Optional[str] = None
    mcp_base_url: str

    model_config = ConfigDict(from_attributes=True)
