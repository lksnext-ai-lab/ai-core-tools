from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


Provider = Literal["system_one", "openai_decisions"]


class SystemOneServiceListItemSchema(BaseModel):
    service_id: int
    name: str
    endpoint: str = ""
    provider: Provider = "system_one"
    supports_images: bool = False
    model: str = ""
    max_concurrency: int = 1
    agent_count: int = 0          # agents that would be left without a service if this one were deleted
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SystemOneServiceDetailSchema(BaseModel):
    service_id: int
    name: str
    endpoint: str = ""
    api_key: str = ""              # always masked on read
    provider: Provider = "system_one"
    supports_images: bool = False
    model: str = ""
    max_concurrency: int = 1
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SystemOneConnectionConfigSchema(BaseModel):
    """What listing the models / testing a connection needs: the wizard asks before a model or a name exist."""
    endpoint: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    api_key: Optional[str] = ""
    provider: Provider = "system_one"
    # Known from the Test step on: lets a server with no model listing be checked with a real call.
    model: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]] = None

    @field_validator("api_key", mode="before")
    @classmethod
    def _strip_credentials(cls, v):
        return v.strip() if isinstance(v, str) else v


class CreateUpdateSystemOneServiceSchema(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    endpoint: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    api_key: Optional[str] = ""    # optional Bearer token; "****…" = keep the stored one, "" = no token
    provider: Provider = "system_one"
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    max_concurrency: Optional[int] = Field(default=None, ge=1)

    @field_validator("api_key", mode="before")
    @classmethod
    def _strip_credentials(cls, v):
        # Trailing whitespace/newlines sneak in when pasting; they break the Authorization header.
        return v.strip() if isinstance(v, str) else v
