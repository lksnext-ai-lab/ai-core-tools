"""API contracts for scheduled-task output providers."""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class OutputProviderDescriptorSchema(BaseModel):
    key: str
    name: str
    supports_links: bool = True
    supports_native_attachments: bool = False
    content_modes: list[str] = ["result", "excerpt", "link_only"]


class OutputDestinationCreateSchema(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider_key: Literal["teams_workflow"] = "teams_workflow"
    webhook_url: str = Field(min_length=1, max_length=4096)


class OutputDestinationUpdateSchema(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    enabled: Optional[bool] = None


class OutputDestinationResponseSchema(BaseModel):
    id: int
    app_id: int
    name: str
    provider_key: str
    enabled: bool
    has_secret: bool
    created_at: datetime
    updated_at: datetime


class OutputDestinationTestResponseSchema(BaseModel):
    accepted: bool = True
    http_status: int


class ScheduledTaskOutputBindingSchema(BaseModel):
    destination_id: int
    enabled: bool = True
    content_mode: Literal["result", "excerpt", "link_only"] = "result"
    destination_name: Optional[str] = None


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
    next_attempt_at: Optional[datetime]
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
