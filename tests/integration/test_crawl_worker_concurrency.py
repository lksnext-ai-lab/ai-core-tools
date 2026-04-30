"""
Integration tests for crawl worker concurrency behaviors.

Tests verify:
  - poll_queued_job claims the next job and sets it to RUNNING
  - A second poll for the same domain does not claim job2 while job1 is RUNNING
  - Two jobs for different domains can be claimed in parallel
  - reset_stuck_jobs recovers RUNNING jobs with stale heartbeats

All tests use real SessionLocal() sessions and commit to the test DB.
Each test cleans up its own data.
"""

import pytest
from datetime import datetime, timedelta

from db.database import SessionLocal
from models.app import App
from models.user import User
from models.domain import Domain
from models.silo import Silo
from models.crawl_job import CrawlJob
from models.crawl_policy import CrawlPolicy
from models.enums.crawl_job_status import CrawlJobStatus
from models.enums.crawl_trigger import CrawlTrigger
from repositories.crawl_job_repository import CrawlJobRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_domain_with_job(db, base_url: str = "http://example.com") -> tuple:
    """
    Create a User, App, Silo, Domain, CrawlPolicy, and a QUEUED CrawlJob.
    Commits to the real DB. Returns (domain_id, job_id, app_id).
    """
    ts = datetime.utcnow().timestamp()
    user = User(
        name="Concurrency Test User",
        email=f"concurrency-test-{ts}@test.com",
        is_active=True,
    )
    db.add(user)
    db.flush()

    app = App(name=f"Concurrency Test App {ts}", owner_id=user.user_id)
    db.add(app)
    db.flush()

    silo = Silo(
        name="Test Silo",
        silo_type="DOMAIN",
        app_id=app.app_id,
        vector_db_type="PGVECTOR",
    )
    db.add(silo)
    db.flush()

    domain = Domain(
        name="Test Domain",
        base_url=base_url,
        app_id=app.app_id,
        silo_id=silo.silo_id,
        content_tag="body",
        create_date=datetime.utcnow(),
    )
    db.add(domain)
    db.flush()

    policy = CrawlPolicy(
        domain_id=domain.domain_id,
        seed_url=base_url,
        manual_urls=[],
        include_globs=[],
        exclude_globs=[],
        rate_limit_rps=1.0,
        refresh_interval_hours=168,
        respect_robots_txt=False,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(policy)
    db.flush()

    job = CrawlJob(
        domain_id=domain.domain_id,
        status=CrawlJobStatus.QUEUED,
        triggered_by=CrawlTrigger.MANUAL,
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    db.commit()

    return domain.domain_id, job.id, app.app_id


def _cleanup_app(app_id: int):
    """Delete test App and all cascade-deleted children."""
    db = SessionLocal()
    try:
        app = db.query(App).filter(App.app_id == app_id).first()
        if app:
            db.delete(app)
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_poll_queued_job_claims_and_sets_running(test_engine):
    """poll_queued_job claims the first QUEUED job and sets it to RUNNING."""
    setup_db = SessionLocal()
    app_id = None
    try:
        domain_id, job_id, app_id = _create_domain_with_job(setup_db)
    finally:
        setup_db.close()

    try:
        db = SessionLocal()
        try:
            claimed = CrawlJobRepository.poll_queued_job("worker-1", db)
            assert claimed is not None
            assert claimed.id == job_id
            assert claimed.status == CrawlJobStatus.RUNNING
            assert claimed.worker_id == "worker-1"
            assert claimed.started_at is not None
        finally:
            db.close()
    finally:
        _cleanup_app(app_id)


def test_two_jobs_same_domain_one_runs_at_a_time(test_engine):
    """
    Two QUEUED jobs for the same domain: worker-1 claims job1 (RUNNING).
    worker-2 should NOT claim job2 since job1 is already RUNNING for that domain.
    """
    setup_db = SessionLocal()
    app_id = None
    try:
        domain_id, job1_id, app_id = _create_domain_with_job(setup_db)

        # Add a second QUEUED job for the same domain
        job2 = CrawlJob(
            domain_id=domain_id,
            status=CrawlJobStatus.QUEUED,
            triggered_by=CrawlTrigger.MANUAL,
            created_at=datetime.utcnow() + timedelta(seconds=1),  # newer
        )
        setup_db.add(job2)
        setup_db.commit()
        job2_id = job2.id
    finally:
        setup_db.close()

    try:
        # Worker 1 claims the first job (oldest QUEUED)
        db1 = SessionLocal()
        try:
            claimed1 = CrawlJobRepository.poll_queued_job("worker-1", db1)
            assert claimed1 is not None
            assert claimed1.id == job1_id
            assert claimed1.status == CrawlJobStatus.RUNNING
        finally:
            db1.close()

        # Worker 2 tries to claim a job — should return None (same domain already RUNNING)
        db2 = SessionLocal()
        try:
            claimed2 = CrawlJobRepository.poll_queued_job("worker-2", db2)
            assert claimed2 is None, (
                f"Expected None (domain already has RUNNING job) but got job {claimed2.id if claimed2 else None}"
            )

            # Verify job2 is still QUEUED
            job2_row = db2.query(CrawlJob).filter(CrawlJob.id == job2_id).first()
            assert job2_row.status == CrawlJobStatus.QUEUED
        finally:
            db2.close()
    finally:
        _cleanup_app(app_id)


def test_two_jobs_different_domains_run_in_parallel(test_engine):
    """
    Jobs for different domains can be claimed by different workers in parallel.
    """
    setup_db = SessionLocal()
    app_id_a = None
    app_id_b = None
    try:
        domain_a_id, job_a_id, app_id_a = _create_domain_with_job(
            setup_db, base_url="http://site-a.com"
        )
        domain_b_id, job_b_id, app_id_b = _create_domain_with_job(
            setup_db, base_url="http://site-b.com"
        )
    finally:
        setup_db.close()

    try:
        # Worker 1 claims job for domain A
        db1 = SessionLocal()
        try:
            claimed_a = CrawlJobRepository.poll_queued_job("worker-1", db1)
            assert claimed_a is not None
            assert claimed_a.status == CrawlJobStatus.RUNNING
        finally:
            db1.close()

        # Worker 2 claims job for domain B (different domain, no conflict)
        db2 = SessionLocal()
        try:
            claimed_b = CrawlJobRepository.poll_queued_job("worker-2", db2)
            assert claimed_b is not None
            assert claimed_b.status == CrawlJobStatus.RUNNING
            # The two claimed jobs should be for different domains
            assert claimed_a.domain_id != claimed_b.domain_id
        finally:
            db2.close()
    finally:
        _cleanup_app(app_id_a)
        _cleanup_app(app_id_b)


def test_stuck_job_recovery(test_engine):
    """
    A RUNNING job with heartbeat_at older than timeout_minutes is reset to QUEUED
    with a note in error_log.
    """
    setup_db = SessionLocal()
    app_id = None
    try:
        domain_id, job_id, app_id = _create_domain_with_job(setup_db)

        # Manually set the job to RUNNING with an old heartbeat (10 minutes ago)
        job = setup_db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        job.status = CrawlJobStatus.RUNNING
        job.started_at = datetime.utcnow() - timedelta(minutes=15)
        job.heartbeat_at = datetime.utcnow() - timedelta(minutes=10)
        job.worker_id = "stale-worker"
        setup_db.commit()
    finally:
        setup_db.close()

    try:
        db = SessionLocal()
        try:
            count = CrawlJobRepository.reset_stuck_jobs(db, timeout_minutes=5)
            assert count >= 1

            # Verify the job is now QUEUED
            job_row = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
            assert job_row.status == CrawlJobStatus.QUEUED
            assert job_row.worker_id is None
            assert job_row.error_log is not None
            assert "recovered" in job_row.error_log.lower()
        finally:
            db.close()
    finally:
        _cleanup_app(app_id)


def test_reset_stuck_jobs_ignores_recent_heartbeat(test_engine):
    """
    A RUNNING job with a recent heartbeat (within timeout) is NOT reset.
    """
    setup_db = SessionLocal()
    app_id = None
    try:
        domain_id, job_id, app_id = _create_domain_with_job(setup_db)

        # Set job to RUNNING with a RECENT heartbeat (1 minute ago)
        job = setup_db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        job.status = CrawlJobStatus.RUNNING
        job.started_at = datetime.utcnow() - timedelta(minutes=2)
        job.heartbeat_at = datetime.utcnow() - timedelta(minutes=1)
        job.worker_id = "active-worker"
        setup_db.commit()
    finally:
        setup_db.close()

    try:
        db = SessionLocal()
        try:
            count = CrawlJobRepository.reset_stuck_jobs(db, timeout_minutes=5)
            # The job should NOT have been reset (heartbeat too recent)
            job_row = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
            assert job_row.status == CrawlJobStatus.RUNNING  # still running
            # count may be 0 or more (other tests might have left stuck jobs, but this one isn't)
        finally:
            db.close()
    finally:
        _cleanup_app(app_id)
