"""Periodic scheduler that enqueues crawl jobs based on policy refresh intervals."""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from models.crawl_job import CrawlJob
from models.enums.crawl_job_status import CrawlJobStatus
from repositories.crawl_job_repository import CrawlJobRepository
from repositories.crawl_policy_repository import CrawlPolicyRepository
from services.crawl_job_service import CrawlJobService, ConflictError
from utils.logger import get_logger

logger = get_logger(__name__)


class CrawlSchedulerService:
    """Evaluates active policies and enqueues new jobs when their refresh interval has elapsed."""

    @staticmethod
    async def run_once(db: Session) -> int:
        """
        Scan active policies and enqueue new crawl jobs as needed.
        Returns the count of jobs enqueued.
        """
        policies = CrawlPolicyRepository.get_domains_due_for_schedule(db)
        enqueued = 0

        for policy in policies:
            if policy.refresh_interval_hours == 0:
                continue

            # Skip if already has an active job
            active = CrawlJobRepository.has_active_job_for_domain(policy.domain_id, db)
            if active:
                continue

            # Check last completed job
            last_job: CrawlJob = (
                db.query(CrawlJob)
                .filter(
                    CrawlJob.domain_id == policy.domain_id,
                    CrawlJob.status == CrawlJobStatus.COMPLETED,
                )
                .order_by(CrawlJob.finished_at.desc())
                .first()
            )

            now = datetime.utcnow()
            should_enqueue = False

            if last_job is None:
                should_enqueue = True
            elif last_job.finished_at is not None:
                next_run = last_job.finished_at + timedelta(hours=policy.refresh_interval_hours)
                if next_run <= now:
                    should_enqueue = True

            if should_enqueue:
                try:
                    CrawlJobService.enqueue(policy.domain_id, triggered_by_user_id=None, db=db)
                    enqueued += 1
                    logger.info(f"Scheduler enqueued job for domain {policy.domain_id}")
                except ConflictError:
                    # Race condition — another worker enqueued first
                    pass
                except Exception as e:
                    logger.error(f"Scheduler failed to enqueue job for domain {policy.domain_id}: {e}")

        return enqueued
