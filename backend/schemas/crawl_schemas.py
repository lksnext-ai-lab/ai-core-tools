from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List
from datetime import datetime


# ==================== CRAWL POLICY SCHEMAS ====================

class CrawlPolicySchema(BaseModel):
    """Request schema for creating or updating a CrawlPolicy."""
    seed_url: Optional[str] = None       # stored as string; validated as URL in service
    sitemap_url: Optional[str] = None
    manual_urls: List[str] = []
    max_depth: int = Field(default=2, ge=0, le=5)
    include_globs: List[str] = []
    exclude_globs: List[str] = []
    rate_limit_rps: float = Field(default=1.0, gt=0, le=10)
    refresh_interval_hours: int = Field(default=168, ge=0, le=720)
    respect_robots_txt: bool = True
    is_active: bool = True


class CrawlPolicyResponseSchema(CrawlPolicySchema):
    """Response schema for a CrawlPolicy."""
    id: int
    domain_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ==================== CRAWL JOB SCHEMAS ====================

class CrawlJobResponseSchema(BaseModel):
    """Response schema for a CrawlJob."""
    id: int
    domain_id: int
    status: str          # CrawlJobStatus value
    triggered_by: str    # CrawlTrigger value
    triggered_by_user_id: Optional[int] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    discovered_count: int = 0
    indexed_count: int = 0
    skipped_count: int = 0
    removed_count: int = 0
    failed_count: int = 0
    error_log: Optional[str] = None
    created_at: Optional[datetime] = None
    worker_id: Optional[str] = None
    heartbeat_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TriggerCrawlResponseSchema(BaseModel):
    """Response after triggering a crawl job."""
    job_id: int
    status: str   # always "QUEUED"


class CrawlJobListResponseSchema(BaseModel):
    """Paginated list of crawl jobs."""
    items: List[CrawlJobResponseSchema]
    page: int
    per_page: int
    total: int


# ==================== DOMAIN URL SCHEMAS ====================

class DomainUrlListItemSchema(BaseModel):
    """Schema for a URL in the list view."""
    id: int
    url: str
    normalized_url: str
    status: str
    discovered_via: str
    depth: int
    content_hash: Optional[str] = None
    last_crawled_at: Optional[datetime] = None
    last_indexed_at: Optional[datetime] = None
    next_crawl_at: Optional[datetime] = None
    consecutive_skips: int = 0
    failure_count: int = 0
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DomainUrlDetailSchema(DomainUrlListItemSchema):
    """Schema for a single URL detail view (includes HTTP cache hints)."""
    domain_id: int
    http_etag: Optional[str] = None
    http_last_modified: Optional[str] = None
    sitemap_lastmod: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DomainUrlListResponseSchema(BaseModel):
    """Paginated list of domain URLs."""
    items: List[DomainUrlListItemSchema]
    page: int
    per_page: int
    total: int


class AddDomainUrlSchema(BaseModel):
    """Request schema for manually adding a URL to a domain."""
    url: str

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('URL cannot be empty')
        return v.strip()


class DomainUrlActionResponseSchema(BaseModel):
    """Generic action response for URL operations."""
    success: bool
    message: str
    url_id: Optional[int] = None
