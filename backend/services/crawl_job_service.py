"""Service for CrawlJob management."""
from typing import List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from models.crawl_job import CrawlJob
from models.enums.crawl_job_status import CrawlJobStatus
from models.enums.crawl_trigger import CrawlTrigger
from repositories.crawl_job_repository import CrawlJobRepository
from utils.error_handlers import ValidationError
from utils.logger import get_logger

logger = get_logger(__name__)


class ConflictError(Exception):
    """Raised when an operation conflicts with existing state (e.g. duplicate active job)."""
    def __init__(self, message: str, job_id: Optional[int] = None):
        self.message = message
        self.job_id = job_id
        super().__init__(message)


class CrawlJobService:
    """Service for managing CrawlJob records."""

    @staticmethod
    def enqueue(domain_id: int, triggered_by_user_id: Optional[int], db: Session) -> CrawlJob:
        """
        Create a new QUEUED crawl job.
        Raises ConflictError if a QUEUED or RUNNING job already exists for this domain.
        """
        active = CrawlJobRepository.has_active_job_for_domain(domain_id, db)
        if active:
            raise ConflictError(
                f"A job is already queued or running for domain {domain_id}.",
                job_id=active.id,
            )

        triggered_by = CrawlTrigger.MANUAL if triggered_by_user_id else CrawlTrigger.SCHEDULED
        job = CrawlJob(
            domain_id=domain_id,
            status=CrawlJobStatus.QUEUED,
            triggered_by=triggered_by,
            triggered_by_user_id=triggered_by_user_id,
            created_at=datetime.utcnow(),
        )
        return CrawlJobRepository.create(job, db)

    @staticmethod
    def cancel(job_id: int, domain_id: int, db: Session) -> CrawlJob:
        """
        Cancel a crawl job.
        Raises ValidationError if the job is already in a terminal state.
        """
        job = CrawlJobRepository.get_by_id(job_id, db)
        if not job or job.domain_id != domain_id:
            raise ValidationError(f"Job {job_id} not found for domain {domain_id}.")

        terminal_states = {CrawlJobStatus.COMPLETED, CrawlJobStatus.FAILED, CrawlJobStatus.CANCELLED}
        if job.status in terminal_states:
            raise ValidationError('Job is already in a terminal state')

        job.status = CrawlJobStatus.CANCELLED
        job.finished_at = datetime.utcnow()
        return CrawlJobRepository.update(job, db)

    @staticmethod
    def get_job(job_id: int, domain_id: int, db: Session) -> Optional[CrawlJob]:
        """Get a crawl job, verifying it belongs to the given domain."""
        job = CrawlJobRepository.get_by_id(job_id, db)
        if job and job.domain_id != domain_id:
            return None
        return job

    @staticmethod
    def list_jobs(domain_id: int, db: Session, page: int = 1, per_page: int = 20) -> Tuple[List[CrawlJob], dict]:
        """List crawl jobs for a domain, newest first."""
        return CrawlJobRepository.get_by_domain_paginated(domain_id, db, page, per_page)

    @staticmethod
    def has_active_job(domain_id: int, db: Session) -> Optional[CrawlJob]:
        """Thin wrapper — returns the active (QUEUED or RUNNING) job for a domain, or None."""
        return CrawlJobRepository.has_active_job_for_domain(domain_id, db)
