"""Core crawl execution logic. Each job runs in a dedicated async task."""
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from urllib.robotparser import RobotFileParser

import aiohttp

from db.database import SessionLocal
from models.crawl_job import CrawlJob
from models.crawl_policy import CrawlPolicy
from models.domain_url import DomainUrl
from models.enums.crawl_job_status import CrawlJobStatus
from models.enums.crawl_trigger import CrawlTrigger
from models.enums.domain_url_status import DomainUrlStatus
from models.enums.discovery_source import DiscoverySource
from repositories.crawl_job_repository import CrawlJobRepository
from repositories.crawl_policy_repository import CrawlPolicyRepository
from repositories.domain_repository import DomainRepository
from repositories.domain_url_repository import DomainUrlRepository
from services.crawl.content_hasher import compute_hash, normalize_text_for_hash
from services.crawl.discovery import discover_urls
from services.crawl.http_fetcher import fetch, FetchResult
from tools.scrapTools import extract_text_from_html
from utils.logger import get_logger

logger = get_logger(__name__)

# Discovery priority order (lower = higher priority — do NOT downgrade)
_SOURCE_PRIORITY = {
    DiscoverySource.MANUAL: 0,
    DiscoverySource.SITEMAP: 1,
    DiscoverySource.CRAWL: 2,
}

HEARTBEAT_INTERVAL_FETCHES = 30


class CrawlExecutorService:
    """Runs a single CrawlJob synchronously (called from async worker context)."""

    @staticmethod
    async def run_job(job_id: int) -> None:
        """
        Execute a crawl job end-to-end.
        Opens its own DB session.
        """
        db = SessionLocal()
        try:
            await CrawlExecutorService._run_job_internal(job_id, db)
        except Exception as e:
            logger.error(f"Unhandled error in CrawlExecutorService.run_job({job_id}): {e}", exc_info=True)
            # Try to mark job as FAILED
            try:
                job = CrawlJobRepository.get_by_id(job_id, db)
                if job and job.status not in {CrawlJobStatus.COMPLETED, CrawlJobStatus.CANCELLED, CrawlJobStatus.FAILED}:
                    job.status = CrawlJobStatus.FAILED
                    job.finished_at = datetime.utcnow()
                    job.error_log = (job.error_log or '') + f"\nUnhandled error: {e}"
                    CrawlJobRepository.update(job, db)
            except Exception:
                pass
        finally:
            db.close()

    @staticmethod
    async def _run_job_internal(job_id: int, db) -> None:
        job = CrawlJobRepository.get_by_id(job_id, db)
        if not job:
            logger.error(f"CrawlJob {job_id} not found")
            return

        domain = DomainRepository.get_by_id(job.domain_id, db)
        if not domain:
            job.status = CrawlJobStatus.FAILED
            job.error_log = "Domain not found"
            job.finished_at = datetime.utcnow()
            CrawlJobRepository.update(job, db)
            return

        policy = CrawlPolicyRepository.get_by_domain(job.domain_id, db)
        if not policy:
            job.status = CrawlJobStatus.FAILED
            job.error_log = "CrawlPolicy not found for domain"
            job.finished_at = datetime.utcnow()
            CrawlJobRepository.update(job, db)
            return

        logger.info(f"Starting job {job_id} for domain {job.domain_id}")

        # Load robots.txt if requested
        robots_parser = None
        if policy.respect_robots_txt and (policy.seed_url or policy.sitemap_url):
            base = policy.seed_url or policy.sitemap_url
            from urllib.parse import urlparse
            parsed = urlparse(base)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            try:
                robots_parser = RobotFileParser(robots_url)
                robots_parser.read()
            except Exception as e:
                logger.warning(f"Could not fetch robots.txt from {robots_url}: {e}")
                robots_parser = None

        # === Phase 1: Discovery ===
        existing_normalized = {
            row.normalized_url
            for row in db.query(DomainUrl).filter(DomainUrl.domain_id == job.domain_id).all()
        }

        async with aiohttp.ClientSession() as session:
            async for candidate in discover_urls(policy, robots_parser, session, existing_normalized):
                # Upsert the candidate, respecting discovery priority
                existing = db.query(DomainUrl).filter(
                    DomainUrl.domain_id == job.domain_id,
                    DomainUrl.normalized_url == candidate.normalized_url,
                ).first()

                if existing:
                    # Only upgrade discovered_via if the new source has higher priority
                    if _SOURCE_PRIORITY.get(candidate.discovered_via, 99) < _SOURCE_PRIORITY.get(existing.discovered_via, 99):
                        existing.discovered_via = candidate.discovered_via
                    if candidate.sitemap_lastmod:
                        existing.sitemap_lastmod = candidate.sitemap_lastmod
                    if candidate.status == DomainUrlStatus.EXCLUDED:
                        existing.status = DomainUrlStatus.EXCLUDED
                        existing.last_error = candidate.last_error
                    db.commit()
                else:
                    new_url = DomainUrl(
                        domain_id=job.domain_id,
                        url=candidate.url,
                        normalized_url=candidate.normalized_url,
                        status=candidate.status,
                        discovered_via=candidate.discovered_via,
                        depth=candidate.depth,
                        sitemap_lastmod=candidate.sitemap_lastmod,
                        last_error=candidate.last_error,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    db.add(new_url)
                    db.commit()
                    job.discovered_count += 1

        # Refresh job counts
        db.refresh(job)

        # === Phase 2: Fetch loop ===
        fetch_urls = db.query(DomainUrl).filter(
            DomainUrl.domain_id == job.domain_id,
            ~DomainUrl.status.in_([DomainUrlStatus.REMOVED, DomainUrlStatus.EXCLUDED]),
        ).all()

        fetch_count = 0
        last_heartbeat = datetime.utcnow()

        async with aiohttp.ClientSession() as session:
            for domain_url in fetch_urls:
                # Check for cancellation
                db.refresh(job)
                if job.status == CrawlJobStatus.CANCELLED:
                    logger.info(f"Job {job_id} cancelled during fetch loop")
                    break

                # Mark as crawling
                domain_url.status = DomainUrlStatus.CRAWLING
                domain_url.last_crawled_at = datetime.utcnow()
                db.commit()

                # Sitemap pre-check: if lastmod matches and already indexed, skip
                if (
                    domain_url.sitemap_lastmod
                    and domain_url.last_indexed_at
                    and domain_url.sitemap_lastmod <= domain_url.last_indexed_at
                    and domain_url.status != DomainUrlStatus.PENDING
                ):
                    domain_url.status = DomainUrlStatus.INDEXED
                    domain_url = _set_skipped_backoff(domain_url, policy)
                    job.skipped_count += 1
                    db.commit()
                    continue

                # Fetch
                result: FetchResult = await fetch(
                    domain_url.url,
                    etag=domain_url.http_etag,
                    last_modified=domain_url.http_last_modified,
                    session=session,
                )

                if result.status_code == 304:
                    # Not modified
                    domain_url.status = DomainUrlStatus.INDEXED
                    domain_url.http_etag = result.etag or domain_url.http_etag
                    domain_url.http_last_modified = result.last_modified or domain_url.http_last_modified
                    domain_url = _set_skipped_backoff(domain_url, policy)
                    job.skipped_count += 1

                elif result.status_code in (404, 410):
                    # Gone — remove from silo
                    if domain and domain.silo_id:
                        try:
                            from services.silo_service import SiloService
                            SiloService.delete_url(domain.silo_id, domain_url.url, db)
                        except Exception as e:
                            logger.warning(f"Silo delete failed for {domain_url.url}: {e}")
                    domain_url.status = DomainUrlStatus.REMOVED
                    domain_url.next_crawl_at = None
                    job.removed_count += 1

                elif result.status_code == 0 or result.status_code >= 500 or result.error:
                    # Error / timeout
                    domain_url.failure_count += 1
                    domain_url.last_error = result.error or f"HTTP {result.status_code}"
                    domain_url.status = DomainUrlStatus.FAILED
                    # Exponential backoff: 2^failure_count hours, max 168
                    if domain_url.failure_count >= 5:
                        domain_url.next_crawl_at = None  # Stop scheduling
                    else:
                        backoff_hours = min(2 ** domain_url.failure_count, 168)
                        domain_url.next_crawl_at = datetime.utcnow() + timedelta(hours=backoff_hours)
                    job.failed_count += 1

                elif result.status_code == 200 and result.content:
                    # Extract text and compute hash
                    text = extract_text_from_html(
                        result.content,
                        tag=domain.content_tag or "body",
                        id=domain.content_id if domain.content_id else None,
                        class_name=domain.content_class if domain.content_class else None,
                    )
                    normalized_text = normalize_text_for_hash(text) if text else ''
                    new_hash = compute_hash(normalized_text) if normalized_text else ''

                    if new_hash and new_hash == domain_url.content_hash:
                        # Content unchanged
                        domain_url.status = DomainUrlStatus.INDEXED
                        domain_url.http_etag = result.etag or domain_url.http_etag
                        domain_url.http_last_modified = result.last_modified or domain_url.http_last_modified
                        domain_url = _set_skipped_backoff(domain_url, policy)
                        job.skipped_count += 1
                    else:
                        # New or changed content — re-vectorize
                        if domain and domain.silo_id and text:
                            try:
                                from services.silo_service import SiloService
                                SiloService.delete_url(domain.silo_id, domain_url.url, db)
                                SiloService.index_single_content(
                                    domain.silo_id,
                                    text,
                                    {"url": domain_url.url, "domain_id": domain.domain_id},
                                    db,
                                )
                            except Exception as e:
                                logger.warning(f"Re-vectorize failed for {domain_url.url}: {e}")
                        domain_url.content_hash = new_hash
                        domain_url.http_etag = result.etag
                        domain_url.http_last_modified = result.last_modified
                        domain_url.last_indexed_at = datetime.utcnow()
                        domain_url.status = DomainUrlStatus.INDEXED
                        domain_url.consecutive_skips = 0
                        if policy.refresh_interval_hours:
                            domain_url.next_crawl_at = datetime.utcnow() + timedelta(hours=policy.refresh_interval_hours)
                        job.indexed_count += 1

                domain_url.updated_at = datetime.utcnow()
                db.commit()

                # Rate limiting
                if policy.rate_limit_rps and policy.rate_limit_rps > 0:
                    await asyncio.sleep(1.0 / policy.rate_limit_rps)

                # Heartbeat every N fetches or 30 seconds
                fetch_count += 1
                now = datetime.utcnow()
                if fetch_count % HEARTBEAT_INTERVAL_FETCHES == 0 or (now - last_heartbeat).total_seconds() >= 30:
                    job.heartbeat_at = now
                    db.commit()
                    last_heartbeat = now

        # Finalize
        db.refresh(job)
        if job.status != CrawlJobStatus.CANCELLED:
            job.status = CrawlJobStatus.COMPLETED if (job.indexed_count + job.skipped_count + job.removed_count) > 0 else CrawlJobStatus.COMPLETED
            job.finished_at = datetime.utcnow()
            db.commit()

        logger.info(
            f"Job {job_id} finished: indexed={job.indexed_count}, "
            f"skipped={job.skipped_count}, removed={job.removed_count}, "
            f"failed={job.failed_count}"
        )


def _set_skipped_backoff(domain_url: DomainUrl, policy: CrawlPolicy) -> DomainUrl:
    """Apply adaptive backoff for a skipped (unchanged) URL."""
    domain_url.consecutive_skips += 1
    multiplier = min(2 ** (domain_url.consecutive_skips // 3), 8)
    effective_hours = min(policy.refresh_interval_hours * multiplier, 720)
    domain_url.next_crawl_at = datetime.utcnow() + timedelta(hours=effective_hours)
    return domain_url
