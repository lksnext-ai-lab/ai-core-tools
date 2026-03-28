from pydantic import BaseModel, ConfigDict
from datetime import datetime


class TierConfigRead(BaseModel):
    """Read schema for a tier limit configuration entry."""
    id: int
    tier: str
    resource_type: str
    limit_value: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TierConfigUpdate(BaseModel):
    """Request body for updating a tier limit configuration entry."""
    tier: str
    resource_type: str
    limit_value: int
