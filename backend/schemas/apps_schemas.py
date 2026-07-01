from pydantic import BaseModel, ConfigDict, field_validator
from typing import Literal, Optional, Dict, Any
from datetime import datetime

class AppUsageStatsSchema(BaseModel):
    usage_percentage: float
    stress_level: str  # "low", "moderate", "high", "critical", "unlimited"
    current_usage: int
    limit: int
    remaining: int
    reset_in_seconds: int
    is_over_limit: bool
    
    model_config = ConfigDict(from_attributes=True)


class AppListItemSchema(BaseModel):
    app_id: int
    name: str
    role: str
    created_at: Optional[datetime] = None
    langsmith_configured: bool
    owner_id: int
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    agent_rate_limit: int
    max_file_size_mb: Optional[int] = 0
    agent_cors_origins: Optional[str] = None
    enable_openai_api: bool = False
    agent_count: int = 0
    repository_count: int = 0
    domain_count: int = 0
    silo_count: int = 0
    collaborator_count: int = 0
    usage_stats: Optional[AppUsageStatsSchema] = None
    is_frozen: bool = False

    model_config = ConfigDict(from_attributes=True)


class AppDetailSchema(BaseModel):
    app_id: int
    name: str
    langsmith_api_key: str
    user_role: str
    created_at: Optional[datetime] = None
    owner_id: int
    owner_email: Optional[str] = None
    owner_name: Optional[str] = None
    agent_rate_limit: int
    max_file_size_mb: Optional[int] = 0
    agent_cors_origins: Optional[str] = None
    enable_openai_api: bool = False
    agent_count: int = 0
    repository_count: int = 0
    domain_count: int = 0
    silo_count: int = 0
    collaborator_count: int = 0
    onboarding_dismissed: bool = False
    is_frozen: bool = False

    model_config = ConfigDict(from_attributes=True)


def _strip_if_string(v):
    # Common normalizer for credentials pasted from emails / .env files /
    # password managers — trailing whitespace breaks HTTP header construction.
    return v.strip() if isinstance(v, str) else v


class CreateAppSchema(BaseModel):
    name: str
    langsmith_api_key: Optional[str] = ""
    agent_rate_limit: Optional[int] = 0
    max_file_size_mb: Optional[int] = 0
    agent_cors_origins: Optional[str] = None

    @field_validator("langsmith_api_key", mode="before")
    @classmethod
    def _strip_credentials(cls, v):
        return _strip_if_string(v)


class UpdateAppSchema(BaseModel):
    name: str
    langsmith_api_key: Optional[str] = ""
    agent_rate_limit: Optional[int] = 0
    max_file_size_mb: Optional[int] = 0
    agent_cors_origins: Optional[str] = None
    enable_openai_api: bool = False

    @field_validator("langsmith_api_key", mode="before")
    @classmethod
    def _strip_credentials(cls, v):
        return _strip_if_string(v)


class LangSmithTestRequestSchema(BaseModel):
    """Schema for testing a LangSmith API key.

    If ``api_key`` is omitted or matches the masked placeholder, the test runs
    against the key already persisted for the app.
    """
    api_key: Optional[str] = None

    @field_validator("api_key", mode="before")
    @classmethod
    def _strip_credentials(cls, v):
        return _strip_if_string(v)


class LangSmithTestResponseSchema(BaseModel):
    """Schema for the LangSmith API key test result."""
    valid: bool
    status: Literal["ok", "unauthorized", "network", "unknown"]
    message: str
    project_name: Optional[str] = None
    source: Optional[Literal["app", "env", "request"]] = None


class CollaboratorListItemSchema(BaseModel):
    id: int
    user_id: int
    user_name: str
    user_email: str
    role: str
    status: str
    invited_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    invited_by_name: Optional[str] = None
    platform_role: str = 'editor'

    model_config = ConfigDict(from_attributes=True)


class CollaboratorDetailSchema(BaseModel):
    id: int
    app_id: int
    user_id: int
    role: str
    status: str
    invited_by: int
    invited_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    user: Optional[Dict[str, Any]] = None
    inviter: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)


class InviteCollaboratorSchema(BaseModel):
    email: str
    role: str = "editor"


class UpdateCollaboratorRoleSchema(BaseModel):
    role: str


class InvitationResponseSchema(BaseModel):
    action: str  # "accept" or "decline"


class CollaborationResponseSchema(BaseModel):
    success: bool
    message: str
    collaborator: Optional[CollaboratorDetailSchema] = None

    model_config = ConfigDict(from_attributes=True)


class OwnershipOfferRequest(BaseModel):
    new_owner_id: int


class OwnershipOfferResponse(BaseModel):
    collaboration_id: int
    app_id: int
    new_owner_id: int
    actor_user_id: int

    model_config = ConfigDict(from_attributes=True)


class OwnershipAcceptResponse(BaseModel):
    """Returned after the recipient accepts; previous_owner_id is now an ADMINISTRATOR collaborator."""

    app_id: int
    name: Optional[str] = None
    new_owner_id: int
    previous_owner_id: int

    model_config = ConfigDict(from_attributes=True)



