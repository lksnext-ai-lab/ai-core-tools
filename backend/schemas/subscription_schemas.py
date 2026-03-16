from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class SubscriptionRead(BaseModel):
    """Current subscription state with usage and limits."""
    tier: str
    billing_status: str
    trial_end: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None
    # Usage
    call_count: int = 0
    call_limit: int = 0
    pct_used: float = 0.0
    # Limits summary
    max_apps: int = 0
    agents_per_app: int = 0
    silos_per_app: int = 0
    skills_per_app: int = 0
    mcp_servers_per_app: int = 0
    collaborators_per_app: int = 0
    admin_override_tier: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CheckoutSessionCreate(BaseModel):
    """Request body for creating a Stripe Checkout session."""
    tier: str  # 'starter' or 'pro'


class PortalSessionResponse(BaseModel):
    """Response with Stripe Customer Portal URL."""
    url: str


class CheckoutSessionResponse(BaseModel):
    """Response with Stripe Checkout URL."""
    url: str
