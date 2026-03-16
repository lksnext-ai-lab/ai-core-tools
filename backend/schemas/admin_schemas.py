from pydantic import BaseModel, ConfigDict
from typing import List, Optional


class UserListResponse(BaseModel):
    users: List[dict]
    total: int
    page: int
    per_page: int
    total_pages: int


class UserDetailResponse(BaseModel):
    user_id: int
    email: str
    name: Optional[str]
    created_at: str
    owned_apps_count: int
    api_keys_count: int
    is_active: bool


class SystemStatsResponse(BaseModel):
    total_users: int
    active_users: int
    inactive_users: int
    total_apps: int
    total_agents: int
    total_api_keys: int
    active_api_keys: int
    inactive_api_keys: int
    recent_users: List[dict]
    users_with_apps: int


class MarketplaceQuotaResetResponse(BaseModel):
    message: str
    user_id: int
    user_email: str
    previous_count: int
    new_count: int
    reset_by: str
    timestamp: str


# ==================== SAAS ADMIN SCHEMAS ====================

class UserAdminRead(BaseModel):
    """Extended user info for OMNIADMIN SaaS dashboard."""
    user_id: int
    email: str
    name: Optional[str]
    is_active: bool
    auth_method: Optional[str] = 'oidc'
    email_verified: bool = True
    tier: Optional[str] = None
    billing_status: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    call_count: int = 0
    call_limit: int = 0
    owned_apps_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class TierOverrideRequest(BaseModel):
    """Request body for OMNIADMIN manual tier override."""
    tier: str  # 'free', 'starter', or 'pro'
