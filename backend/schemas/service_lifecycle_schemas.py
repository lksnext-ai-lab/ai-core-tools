"""Shared end-of-service schema fragments for AI, embedding and sandbox services."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from utils.service_lifecycle import MAX_DEPRECATION_NOTICE_LENGTH, normalize_deprecation_notice, to_utc


class ServiceLifecycleFieldsMixin(BaseModel):
    """Editable end-of-service fields (create/update payloads and export files).

    ``lifecycle_status`` is read-only and deliberately not part of this mixin. Services only apply
    a field that is in ``model_fields_set``, so omitting it keeps the stored value.
    """

    end_of_service_at: Optional[datetime] = None
    deprecation_notice: Optional[str] = Field(None, max_length=MAX_DEPRECATION_NOTICE_LENGTH)

    @field_validator("end_of_service_at", mode="after")
    @classmethod
    def _end_of_service_to_utc(cls, v):
        return to_utc(v)

    @field_validator("deprecation_notice", mode="before")
    @classmethod
    def _clean_deprecation_notice(cls, v):
        return normalize_deprecation_notice(v) if isinstance(v, str) else v


class ServiceLifecycleWarningSchema(BaseModel):
    """A deprecated or retired service a resource depends on (directly or through a silo / middleware)."""

    service_id: int
    service_name: str
    kind: Literal["ai", "embedding", "sandbox"]
    role: Literal[
        "llm", "ocr_vision", "transcription", "video", "media_embedding", "silo_embedding", "middleware", "embedding",
        "sandbox",
    ]
    # Silo name (role silo_embedding), middleware name (role middleware) or "app default" (role sandbox).
    via: Optional[str] = None
    lifecycle_status: Literal["deprecated", "retired"]
    end_of_service_at: datetime
    deprecation_notice: Optional[str] = None


# ==================== "Used by" and bulk service usage moves ====================

ServiceUsageKind = Literal["ai", "embedding", "sandbox"]
AgentUsageRole = Literal[
    "llm", "ocr_vision", "transcription", "video", "media_embedding", "silo_embedding", "sandbox",
    "sandbox_app_default",
]
SiloUsageRole = Literal["embedding", "transcription", "video"]
ServiceLifecycleStatusLiteral = Literal["active", "deprecated", "retired"]


class ServiceUsageAgentSchema(BaseModel):
    agent_id: int
    name: str
    roles: List[AgentUsageRole]
    app_id: int
    # Only filled in the admin (cross-app) view.
    app_name: Optional[str] = None


class ServiceUsageSiloSchema(BaseModel):
    silo_id: int
    name: str
    roles: List[SiloUsageRole]
    app_id: int
    app_name: Optional[str] = None


class ServiceUsageRepositorySchema(BaseModel):
    repository_id: int
    name: str
    silo_id: int
    app_id: int
    app_name: Optional[str] = None


class ServiceUsageMiddlewareSchema(BaseModel):
    middleware_id: int
    name: str
    middleware_type: str
    agent_ids: List[int] = Field(default_factory=list)
    app_id: int
    app_name: Optional[str] = None


class ServiceUsageScheduledTaskSchema(BaseModel):
    task_id: int
    name: str
    agent_id: int
    app_id: int
    app_name: Optional[str] = None


class ServiceUsageAppSchema(BaseModel):
    """An app that uses a sandbox service as its default."""

    app_id: int
    app_name: str


class ServiceUsageSchema(BaseModel):
    """Who depends on a service. Extended by the sandbox step with further lists."""

    service_id: int
    service_name: str
    kind: ServiceUsageKind
    is_system: bool
    lifecycle_status: ServiceLifecycleStatusLiteral
    end_of_service_at: Optional[datetime] = None
    deprecation_notice: Optional[str] = None
    agents: List[ServiceUsageAgentSchema] = Field(default_factory=list)
    silos: List[ServiceUsageSiloSchema] = Field(default_factory=list)
    repositories: List[ServiceUsageRepositorySchema] = Field(default_factory=list)
    middlewares: List[ServiceUsageMiddlewareSchema] = Field(default_factory=list)
    scheduled_tasks: List[ServiceUsageScheduledTaskSchema] = Field(default_factory=list)
    # Sandbox services only: apps that use the service as their default sandbox.
    apps_using_as_default: List[ServiceUsageAppSchema] = Field(default_factory=list)


class MoveAgentsRequestSchema(BaseModel):
    target_service_id: int
    # Number of agents the user saw and confirmed; a different current count aborts with 409.
    expected_count: Optional[int] = Field(None, ge=0)


class MoveAgentsResponseSchema(BaseModel):
    moved_agent_ids: List[int]
    count: int


class MoveSandboxUsageRequestSchema(BaseModel):
    target_service_id: int
    expected_agent_count: int = Field(..., ge=0)
    expected_app_count: int = Field(..., ge=0)


class MoveSandboxUsageResponseSchema(BaseModel):
    moved_agent_ids: List[int]
    updated_app_ids: List[int]
