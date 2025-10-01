from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime

# ==================== APP SCHEMAS ====================

class AppListItemSchema(BaseModel):
    """Schema for app list items"""
    app_id: int
    name: str
    role: str  # "owner", "admin", "member"
    created_at: Optional[datetime]
    langsmith_configured: bool
    owner_id: int
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    agent_rate_limit: int
    # Entity counts for table display

    agent_count: int = 0
    repository_count: int = 0
    domain_count: int = 0
    silo_count: int = 0
    collaborator_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)


class AppDetailSchema(BaseModel):
    """Schema for detailed app information"""
    app_id: int
    name: str
    langsmith_api_key: str
    user_role: str
    created_at: Optional[datetime]
    owner_id: int
    agent_rate_limit: int
    # Entity counts for dashboard display
     
    agent_count: int = 0
    repository_count: int = 0
    domain_count: int = 0
    silo_count: int = 0
    collaborator_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)


class CreateAppSchema(BaseModel):
    """Schema for creating a new app"""
    name: str
    langsmith_api_key: Optional[str] = ""
    agent_rate_limit: Optional[int] = 0


class UpdateAppSchema(BaseModel):
    """Schema for updating an app"""
    name: str
    langsmith_api_key: Optional[str] = ""
    agent_rate_limit: Optional[int] = 0


# ==================== COLLABORATION SCHEMAS ====================

class CollaboratorListItemSchema(BaseModel):
    """Schema for collaborator list items"""
    id: int
    user_id: int
    user_name: str
    user_email: str
    role: str
    status: str
    invited_at: Optional[datetime]
    accepted_at: Optional[datetime]
    invited_by_name: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)


class CollaboratorDetailSchema(BaseModel):
    """Schema for detailed collaborator information"""
    id: int
    app_id: int
    user_id: int
    role: str
    status: str
    invited_by: int
    invited_at: Optional[datetime]
    accepted_at: Optional[datetime]
    user: Optional[Dict[str, Any]] = None
    inviter: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)


class InviteCollaboratorSchema(BaseModel):
    """Schema for inviting a collaborator"""
    email: str
    role: str = "editor"  # "admin", "editor", "viewer"


class UpdateCollaboratorRoleSchema(BaseModel):
    """Schema for updating collaborator role"""
    role: str  # "admin", "editor", "viewer"


class InvitationResponseSchema(BaseModel):
    """Schema for responding to collaboration invitations"""
    action: str  # "accept" or "decline"


class CollaborationResponseSchema(BaseModel):
    """Schema for collaboration response"""
    success: bool
    message: str
    collaborator: Optional[CollaboratorDetailSchema] = None
    
    model_config = ConfigDict(from_attributes=True)



