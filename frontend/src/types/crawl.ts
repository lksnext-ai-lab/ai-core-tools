/**
 * TypeScript interfaces for the domain crawling policies feature.
 * Mirrors the Pydantic schemas in backend/schemas/crawl_schemas.py.
 */

export type DomainUrlStatus =
  | 'PENDING'
  | 'CRAWLING'
  | 'INDEXED'
  | 'SKIPPED'
  | 'FAILED'
  | 'REMOVED'
  | 'EXCLUDED';

export type DiscoverySource = 'SITEMAP' | 'CRAWL' | 'MANUAL';

export type CrawlJobStatus = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

export type CrawlTrigger = 'MANUAL' | 'SCHEDULED';

// ---------------------------------------------------------------------------
// CrawlPolicy
// ---------------------------------------------------------------------------

export interface CrawlPolicy {
  id: number;
  domain_id: number;
  seed_url: string | null;
  sitemap_url: string | null;
  manual_urls: string[];
  max_depth: number;
  include_globs: string[];
  exclude_globs: string[];
  rate_limit_rps: number;
  refresh_interval_hours: number;
  respect_robots_txt: boolean;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

/** Input shape for creating or updating a CrawlPolicy (excludes server-managed fields). */
export type CrawlPolicyInput = Omit<CrawlPolicy, 'id' | 'domain_id' | 'created_at' | 'updated_at'>;

// ---------------------------------------------------------------------------
// CrawlJob
// ---------------------------------------------------------------------------

export interface CrawlJob {
  id: number;
  domain_id: number;
  status: CrawlJobStatus;
  triggered_by: CrawlTrigger;
  triggered_by_user_id: number | null;
  started_at: string | null;
  finished_at: string | null;
  discovered_count: number;
  indexed_count: number;
  skipped_count: number;
  removed_count: number;
  failed_count: number;
  error_log: string | null;
  created_at: string | null;
  worker_id: string | null;
  heartbeat_at: string | null;
}

export interface CrawlJobListResponse {
  items: CrawlJob[];
  page: number;
  per_page: number;
  total: number;
}

export interface TriggerCrawlResponse {
  job_id: number;
  status: string; // always "QUEUED"
}

// ---------------------------------------------------------------------------
// DomainUrl
// ---------------------------------------------------------------------------

export interface DomainUrl {
  id: number;
  url: string;
  normalized_url: string;
  status: DomainUrlStatus;
  discovered_via: DiscoverySource;
  depth: number;
  content_hash: string | null;
  last_crawled_at: string | null;
  last_indexed_at: string | null;
  next_crawl_at: string | null;
  consecutive_skips: number;
  failure_count: number;
  last_error: string | null;
  created_at: string | null;
}

export interface DomainUrlDetail extends DomainUrl {
  domain_id: number;
  http_etag: string | null;
  http_last_modified: string | null;
  sitemap_lastmod: string | null;
  updated_at: string | null;
}

export interface DomainUrlListResponse {
  items: DomainUrl[];
  page: number;
  per_page: number;
  total: number;
}

export interface DomainUrlActionResponse {
  success: boolean;
  message: string;
  url_id?: number;
}
