from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models.crawl_job import CrawlJob
from models.enums.crawl_job_status import CrawlJobStatus
from utils.logger import get_logger

logger = get_logger(__name__)


class CrawlJobRepository:
    """Repository for CrawlJob data access operations."""

    @staticmethod
    def get_by_id(job_id: int, db: Session) -> Optional[CrawlJob]:
        return db.query(CrawlJob).filter(CrawlJob.id == job_id).first()

    @staticmethod
    def get_by_domain_paginated(
        domain_id: int,
        db: Session,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[CrawlJob], dict]:
        query = (
            db.query(CrawlJob)
            .filter(CrawlJob.domain_id == domain_id)
            .order_by(CrawlJob.created_at.desc())
        )
        total = query.count()
        offset = (page - 1) * per_page
        items = query.offset(offset).limit(per_page).all()
        pagination_info = {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page if per_page > 0 else 0,
        }
        return items, pagination_info

    @staticmethod
    def create(job: CrawlJob, db: Session) -> CrawlJob:
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def update(job: CrawlJob, db: Session) -> CrawlJob:
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def has_active_job_for_domain(domain_id: int, db: Session) -> Optional[CrawlJob]:
        """Returns the first QUEUED or RUNNING job for the domain, or None."""
        return (
            db.query(CrawlJob)
            .filter(
                CrawlJob.domain_id == domain_id,
                CrawlJob.status.in_([CrawlJobStatus.QUEUED, CrawlJobStatus.RUNNING]),
            )
            .first()
        )

    @staticmethod
    def poll_queued_job(worker_id: str, db: Session) -> Optional[CrawlJob]:
        """
        Claims the next QUEUED job for this worker using SELECT ... FOR UPDATE SKIP LOCKED.
        Only claims the job if no other RUNNING job exists for the same domain.
        Returns the job if claimed, else None.
        """
        job = (
            db.query(CrawlJob)
            .filter(CrawlJob.status == CrawlJobStatus.QUEUED)
            .order_by(CrawlJob.created_at)
            .with_for_update(skip_locked=True)
            .first()
        )
        if job is None:
            return None

        # Check if a RUNNING job already exists for this domain
        running_exists = (
            db.query(CrawlJob)
            .filter(
                CrawlJob.domain_id == job.domain_id,
                CrawlJob.status == CrawlJobStatus.RUNNING,
            )
            .first()
        )
        if running_exists:
            # Release lock — do not claim this job
            db.rollback()
            return None

        # Claim the job
        job.status = CrawlJobStatus.RUNNING
        job.worker_id = worker_id
        job.started_at = datetime.utcnow()
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def reset_stuck_jobs(db: Session, timeout_minutes: int = 5) -> int:
        """
        Finds RUNNING jobs whose heartbeat is older than timeout_minutes and resets them to QUEUED.
        Returns the number of jobs reset.
        """
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        stuck_jobs = (
            db.query(CrawlJob)
            .filter(
                CrawlJob.status == CrawlJobStatus.RUNNING,
                CrawlJob.heartbeat_at < cutoff,
            )
            .all()
        )
        count = 0
        for job in stuck_jobs:
            job.status = CrawlJobStatus.QUEUED
            job.worker_id = None
            old_log = job.error_log or ''
            job.error_log = (
                old_log
                + f"\n[recovered at {datetime.utcnow().isoformat()}] Job reset from RUNNING to QUEUED due to missed heartbeat."
            ).lstrip()
            count += 1

        if count:
            db.commit()
            logger.info(f"Reset {count} stuck crawl job(s) to QUEUED.")

        return count
