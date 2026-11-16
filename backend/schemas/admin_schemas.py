from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserListResponse(BaseModel):
    users: List[dict]
    total: int
    page: int
    per_page: int
    total_pages: int


class UserDetailIdentity(BaseModel):
    user_id: int
    email: Optional[str] = None
    name: Optional[str] = None
    created_at: Optional[datetime] = None
    is_active: bool
    auth_method: Optional[str] = None
    email_verified: bool
    platform_role: Optional[str] = None
    is_omniadmin: bool = False

    model_config = ConfigDict(from_attributes=True)


class UserDetailOwnedApp(BaseModel):
    app_id: int
    name: Optional[str] = None
    is_frozen: bool

    model_config = ConfigDict(from_attributes=True)


class UserDetailCollaboration(BaseModel):
    app_id: int
    app_name: Optional[str] = None
    role: str
    status: str
    invited_at: datetime
    accepted_at: Optional[datetime] = None
    is_frozen: bool

    model_config = ConfigDict(from_attributes=True)


class UserDetailAPIKey(BaseModel):
    key_id: int
    name: str
    app_id: int
    app_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserDetailUsage(BaseModel):
    """System LLM calls recorded for the user during the billing period."""

    call_count: int = Field(
        description="System LLM calls recorded for this user during this billing period."
    )
    billing_period_start: date

    model_config = ConfigDict(from_attributes=True)


class UserDetailResponse(BaseModel):
    identity: UserDetailIdentity
    owned_apps: List[UserDetailOwnedApp]
    collaborations: List[UserDetailCollaboration]
    api_keys: List[UserDetailAPIKey]
    usage: UserDetailUsage

    model_config = ConfigDict(from_attributes=True)


class SetPlatformRoleRequest(BaseModel):
    role: str


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


class TransferOwnerRequest(BaseModel):
    """Request body for OMNIADMIN administrative-direct ownership transfer."""

    new_owner_id: int


class AppTransferSummary(BaseModel):
    """Minimal app summary returned after an ownership transfer."""

    app_id: int
    name: Optional[str] = None
    previous_owner_id: int
    new_owner_id: int

    model_config = ConfigDict(from_attributes=True)


class DeleteUserRequest(BaseModel):
    """Optional body for ``DELETE /admin/users/{user_id}``; defaults to mode='block'.

    mode: 'block' — 409 if user owns apps; 'cascade_apps' — delete all owned apps first;
    'transfer_apps' — reassign owned apps to transfer_to_user_id, then delete user.
    """

    mode: Literal["block", "cascade_apps", "transfer_apps"] = "block"
    transfer_to_user_id: Optional[int] = None


class OwnedAppConflictItem(BaseModel):
    app_id: int
    name: str


class OwnedAppsConflictResponse(BaseModel):
    """HTTP 409 body when deleting a user who owns apps with mode='block'."""

    detail: str
    owned_apps: List[OwnedAppConflictItem]
