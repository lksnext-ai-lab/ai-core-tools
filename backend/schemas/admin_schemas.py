from pydantic import BaseModel
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
    total_apps: int
    total_agents: int
    total_api_keys: int
    active_api_keys: int
    inactive_api_keys: int
    recent_users: List[dict]
    users_with_apps: int
