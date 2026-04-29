"""
Integration tests for the crawl job API endpoints.

Endpoints under test:
  POST /internal/apps/{app_id}/domains/{domain_id}/crawl-jobs
  GET  /internal/apps/{app_id}/domains/{domain_id}/crawl-jobs
  GET  /internal/apps/{app_id}/domains/{domain_id}/crawl-jobs/{job_id}
  POST /internal/apps/{app_id}/domains/{domain_id}/crawl-jobs/{job_id}/cancel
"""

import pytest
from datetime import datetime

from models.crawl_job import CrawlJob
from models.enums.crawl_job_status import CrawlJobStatus
from models.enums.crawl_trigger import CrawlTrigger


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTriggerCrawl:
    """POST /internal/apps/{app_id}/domains/{domain_id}/crawl-jobs"""

    def test_trigger_creates_queued_job(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Triggering a crawl creates a QUEUED job and returns 202."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs",
            headers=owner_headers,
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "QUEUED"
        assert "job_id" in data
        assert isinstance(data["job_id"], int)

    def test_trigger_while_queued_returns_409(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """A second trigger while a job is already QUEUED returns 409."""
        db.flush()
        # First trigger
        r1 = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs",
            headers=owner_headers,
        )
        assert r1.status_code == 202

        # Second trigger while first is still QUEUED
        r2 = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs",
            headers=owner_headers,
        )
        assert r2.status_code == 409
        data = r2.json()
        assert "job_id" in data["detail"]

    def test_trigger_nonexistent_domain_returns_404(
        self, client, fake_app, owner_headers, db
    ):
        """Triggering a crawl for a non-existent domain returns 404."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/99999/crawl-jobs",
            headers=owner_headers,
        )
        assert response.status_code == 404


class TestGetCrawlJob:
    """GET /internal/apps/{app_id}/domains/{domain_id}/crawl-jobs/{job_id}"""

    def test_get_job_returns_correct_status(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """GET a crawl job returns full job details including status."""
        db.flush()
        # Create a job via the API
        trigger_resp = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs",
            headers=owner_headers,
        )
        assert trigger_resp.status_code == 202
        job_id = trigger_resp.json()["job_id"]

        # Fetch the job
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs/{job_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job_id
        assert data["domain_id"] == fake_domain.domain_id
        assert data["status"] == "QUEUED"
        assert data["triggered_by"] == "MANUAL"

    def test_get_nonexistent_job_returns_404(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """GET a non-existent job returns 404."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs/99999",
            headers=owner_headers,
        )
        assert response.status_code == 404


class TestListCrawlJobs:
    """GET /internal/apps/{app_id}/domains/{domain_id}/crawl-jobs"""

    def test_list_jobs_empty(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Listing jobs for a domain with no jobs returns empty list."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs",
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_jobs_pagination(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Insert 5 jobs, list with per_page=2 returns 2 items and total=5."""
        db.flush()
        # Insert 5 QUEUED jobs directly into DB
        for _ in range(5):
            job = CrawlJob(
                domain_id=fake_domain.domain_id,
                status=CrawlJobStatus.QUEUED,
                triggered_by=CrawlTrigger.MANUAL,
                created_at=datetime.utcnow(),
            )
            db.add(job)
        db.flush()

        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs"
            f"?page=1&per_page=2",
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["per_page"] == 2

    def test_list_jobs_second_page(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Second page of paginated job list has the remaining items."""
        db.flush()
        for _ in range(5):
            job = CrawlJob(
                domain_id=fake_domain.domain_id,
                status=CrawlJobStatus.QUEUED,
                triggered_by=CrawlTrigger.MANUAL,
                created_at=datetime.utcnow(),
            )
            db.add(job)
        db.flush()

        response = client.get(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs"
            f"?page=2&per_page=2",
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5


class TestCancelCrawlJob:
    """POST /internal/apps/{app_id}/domains/{domain_id}/crawl-jobs/{job_id}/cancel"""

    def test_cancel_queued_job(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Cancelling a QUEUED job transitions it to CANCELLED."""
        db.flush()
        # Create a job via the API
        trigger_resp = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs",
            headers=owner_headers,
        )
        assert trigger_resp.status_code == 202
        job_id = trigger_resp.json()["job_id"]

        # Cancel it
        cancel_resp = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs/{job_id}/cancel",
            headers=owner_headers,
        )
        assert cancel_resp.status_code == 200
        data = cancel_resp.json()
        assert data["status"] == "CANCELLED"
        assert data["id"] == job_id

    def test_cancel_completed_job_returns_409(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Cancelling a COMPLETED job returns 409 (terminal state)."""
        db.flush()
        # Insert a COMPLETED job directly
        job = CrawlJob(
            domain_id=fake_domain.domain_id,
            status=CrawlJobStatus.COMPLETED,
            triggered_by=CrawlTrigger.MANUAL,
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
        )
        db.add(job)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs/{job.id}/cancel",
            headers=owner_headers,
        )
        assert response.status_code == 409

    def test_cancel_failed_job_returns_409(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Cancelling a FAILED job returns 409 (terminal state)."""
        db.flush()
        job = CrawlJob(
            domain_id=fake_domain.domain_id,
            status=CrawlJobStatus.FAILED,
            triggered_by=CrawlTrigger.MANUAL,
            created_at=datetime.utcnow(),
        )
        db.add(job)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs/{job.id}/cancel",
            headers=owner_headers,
        )
        assert response.status_code == 409

    def test_cancel_already_cancelled_job_returns_409(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Cancelling an already-CANCELLED job returns 409."""
        db.flush()
        job = CrawlJob(
            domain_id=fake_domain.domain_id,
            status=CrawlJobStatus.CANCELLED,
            triggered_by=CrawlTrigger.MANUAL,
            created_at=datetime.utcnow(),
        )
        db.add(job)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs/{job.id}/cancel",
            headers=owner_headers,
        )
        assert response.status_code == 409

    def test_cancel_nonexistent_job_returns_404(
        self, client, fake_app, fake_domain, owner_headers, db
    ):
        """Cancelling a non-existent job returns 404."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/domains/{fake_domain.domain_id}/crawl-jobs/99999/cancel",
            headers=owner_headers,
        )
        assert response.status_code == 404
