"""Service for CrawlPolicy management."""
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session

from models.crawl_policy import CrawlPolicy
from repositories.crawl_policy_repository import CrawlPolicyRepository
from schemas.crawl_schemas import CrawlPolicySchema
from services.crawl.glob_matcher import validate_globs
from utils.error_handlers import ValidationError
from utils.logger import get_logger

logger = get_logger(__name__)


class CrawlPolicyService:
    """Service for managing CrawlPolicy records."""

    @staticmethod
    def get_policy(domain_id: int, db: Session) -> Optional[CrawlPolicy]:
        """Get the crawl policy for a domain."""
        return CrawlPolicyRepository.get_by_domain(domain_id, db)

    @staticmethod
    def upsert_policy(domain_id: int, data: CrawlPolicySchema, db: Session) -> CrawlPolicy:
        """
        Validate and upsert a CrawlPolicy for the given domain.
        Raises ValidationError if business rules are violated.
        """
        # Business rule: at least one discovery source must be configured
        has_seed = bool(data.seed_url and data.seed_url.strip())
        has_sitemap = bool(data.sitemap_url and data.sitemap_url.strip())
        has_manual = bool(data.manual_urls)
        if not (has_seed or has_sitemap or has_manual):
            raise ValidationError(
                "At least one discovery source must be configured (seed_url, sitemap_url, or manual_urls).",
                field="discovery_source",
            )

        # Validate globs
        invalid_include = validate_globs(data.include_globs or [])
        if invalid_include:
            raise ValidationError(
                f"Invalid include_globs patterns: {invalid_include}",
                field="include_globs",
            )
        invalid_exclude = validate_globs(data.exclude_globs or [])
        if invalid_exclude:
            raise ValidationError(
                f"Invalid exclude_globs patterns: {invalid_exclude}",
                field="exclude_globs",
            )

        # Upsert
        policy = CrawlPolicyRepository.get_by_domain(domain_id, db)
        now = datetime.utcnow()

        if policy:
            policy.seed_url = data.seed_url
            policy.sitemap_url = data.sitemap_url
            policy.manual_urls = data.manual_urls
            policy.max_depth = data.max_depth
            policy.include_globs = data.include_globs
            policy.exclude_globs = data.exclude_globs
            policy.rate_limit_rps = data.rate_limit_rps
            policy.refresh_interval_hours = data.refresh_interval_hours
            policy.respect_robots_txt = data.respect_robots_txt
            policy.is_active = data.is_active
            policy.updated_at = now
            return CrawlPolicyRepository.update(policy, db)
        else:
            policy = CrawlPolicy(
                domain_id=domain_id,
                seed_url=data.seed_url,
                sitemap_url=data.sitemap_url,
                manual_urls=data.manual_urls,
                max_depth=data.max_depth,
                include_globs=data.include_globs,
                exclude_globs=data.exclude_globs,
                rate_limit_rps=data.rate_limit_rps,
                refresh_interval_hours=data.refresh_interval_hours,
                respect_robots_txt=data.respect_robots_txt,
                is_active=data.is_active,
                created_at=now,
                updated_at=now,
            )
            return CrawlPolicyRepository.create(policy, db)

    @staticmethod
    def get_or_create_default(domain_id: int, base_url: str, db: Session) -> CrawlPolicy:
        """
        Return the existing policy for a domain, or create an inactive default
        with seed_url=base_url. Called during domain creation.
        """
        policy = CrawlPolicyRepository.get_by_domain(domain_id, db)
        if policy:
            return policy

        now = datetime.utcnow()
        policy = CrawlPolicy(
            domain_id=domain_id,
            seed_url=base_url,
            sitemap_url=None,
            manual_urls=[],
            max_depth=2,
            include_globs=[],
            exclude_globs=[],
            rate_limit_rps=1.0,
            refresh_interval_hours=168,
            respect_robots_txt=True,
            is_active=False,
            created_at=now,
            updated_at=now,
        )
        return CrawlPolicyRepository.create(policy, db)
