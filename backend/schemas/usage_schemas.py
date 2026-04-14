from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import date


class UsageRead(BaseModel):
    """Current system LLM usage for the authenticated user."""
    call_count: int
    call_limit: int
    period_start: Optional[date] = None
    pct_used: float  # 0.0–1.0 (can exceed 1.0 if over limit)

    model_config = ConfigDict(from_attributes=True)
