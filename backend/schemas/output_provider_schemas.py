"""API contracts for scheduled-task output providers."""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class OutputProviderDescriptorSchema(BaseModel):
    key: str
    name: str
    supports_links: bool = True
    supports_native_attachments: bool = False
    supports_binary_attachments: bool = False
    content_modes: list[str] = ["result", "excerpt", "link_only"]


class OutputDestinationCreateSchema(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider_key: Literal["teams_workflow", "webhook"] = "teams_workflow"
    webhook_url: str = Field(min_length=1, max_length=4096)
    content_mode: Literal["result", "excerpt", "link_only"] = "result"
    public_config: dict[str, Any] = Field(default_factory=dict)
    credentials: Optional[dict[str, str]] = None


class OutputDestinationUpdateSchema(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    enabled: Optional[bool] = None
    content_mode: Optional[Literal["result", "excerpt", "link_only"]] = None
    webhook_url: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    public_config: Optional[dict[str, Any]] = None
    credentials: Optional[dict[str, str]] = None
    clear_credentials: bool = False


class OutputDestinationResponseSchema(BaseModel):
    id: int
    app_id: int
    name: str
    provider_key: str
    enabled: bool
    content_mode: Literal["result", "excerpt", "link_only"] = "result"
    has_secret: bool
    public_config: dict[str, Any] = Field(default_factory=dict)
    has_credentials: bool = False
    created_at: datetime
    updated_at: datetime


class OutputDestinationTestResponseSchema(BaseModel):
    accepted: bool = True
    http_status: int
    event_id: Optional[str] = None


class ScheduledTaskOutputBindingSchema(BaseModel):
    destination_id: int
    enabled: bool = True
    destination_name: Optional[str] = None
    provider_key: Optional[str] = None
    include_attachments: bool = False


class ScheduledTaskOutputBindingsRequestSchema(BaseModel):
    bindings: list[ScheduledTaskOutputBindingSchema] = Field(default_factory=list, max_length=20)


class OutputDeliveryAttemptResponseSchema(BaseModel):
    attempt_number: int
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    http_status: Optional[int] = None
    error_summary: Optional[str] = None


class OutputDeliveryResponseSchema(BaseModel):
    id: int
    destination_name: str
    provider_key: str
    event_type: str
    status: str
    attempt_count: int
    next_attempt_at: Optional[datetime] = None
    receipt: Optional[dict[str, Any]] = None
    error_summary: Optional[str] = None
    created_at: datetime
    attempts: list[OutputDeliveryAttemptResponseSchema] = Field(default_factory=list)


class OutputDeliveryListResponseSchema(BaseModel):
    deliveries: list[OutputDeliveryResponseSchema]


class OutputDeliveryRetryResponseSchema(BaseModel):
    delivery_id: int
    status: str = "queued"
    workflow_id: str


class OutputBindingsResponseSchema(BaseModel):
    bindings: list[ScheduledTaskOutputBindingSchema]
