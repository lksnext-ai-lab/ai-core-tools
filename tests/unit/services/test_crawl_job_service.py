"""Unit tests for CrawlJobService."""
import pytest
from unittest.mock import MagicMock, patch

from models.enums.crawl_job_status import CrawlJobStatus
from services.crawl_job_service import CrawlJobService, ConflictError
from utils.error_handlers import ValidationError


class TestCrawlJobServiceEnqueue:
    """Test CrawlJobService.enqueue method."""

    def test_enqueue_with_no_active_job_creates_job(self):
        db = MagicMock()
        mock_job = MagicMock()

        with patch('services.crawl_job_service.CrawlJobRepository') as mock_repo:
            mock_repo.has_active_job_for_domain.return_value = None
            mock_repo.create.return_value = mock_job
            result = CrawlJobService.enqueue(domain_id=1, triggered_by_user_id=42, db=db)
            assert mock_repo.create.called
            assert result is mock_job

    def test_enqueue_with_active_job_raises_conflict(self):
        db = MagicMock()
        active_job = MagicMock()
        active_job.id = 99

        with patch('services.crawl_job_service.CrawlJobRepository') as mock_repo:
            mock_repo.has_active_job_for_domain.return_value = active_job
            with pytest.raises(ConflictError) as exc_info:
                CrawlJobService.enqueue(domain_id=1, triggered_by_user_id=None, db=db)
            assert exc_info.value.job_id == 99

    def test_enqueue_with_user_id_uses_manual_trigger(self):
        from models.enums.crawl_trigger import CrawlTrigger
        db = MagicMock()
        mock_job = MagicMock()

        with patch('services.crawl_job_service.CrawlJobRepository') as mock_repo:
            mock_repo.has_active_job_for_domain.return_value = None
            mock_repo.create.return_value = mock_job

            CrawlJobService.enqueue(domain_id=1, triggered_by_user_id=5, db=db)
            created_job = mock_repo.create.call_args[0][0]
            assert created_job.triggered_by == CrawlTrigger.MANUAL

    def test_enqueue_without_user_id_uses_scheduled_trigger(self):
        from models.enums.crawl_trigger import CrawlTrigger
        db = MagicMock()
        mock_job = MagicMock()

        with patch('services.crawl_job_service.CrawlJobRepository') as mock_repo:
            mock_repo.has_active_job_for_domain.return_value = None
            mock_repo.create.return_value = mock_job

            CrawlJobService.enqueue(domain_id=1, triggered_by_user_id=None, db=db)
            created_job = mock_repo.create.call_args[0][0]
            assert created_job.triggered_by == CrawlTrigger.SCHEDULED


class TestCrawlJobServiceCancel:
    """Test CrawlJobService.cancel method."""

    def _make_job(self, status):
        job = MagicMock()
        job.id = 1
        job.domain_id = 10
        job.status = status
        return job

    def test_cancel_queued_job_sets_cancelled(self):
        db = MagicMock()
        job = self._make_job(CrawlJobStatus.QUEUED)

        with patch('services.crawl_job_service.CrawlJobRepository') as mock_repo:
            mock_repo.get_by_id.return_value = job
            mock_repo.update.return_value = job
            result = CrawlJobService.cancel(job_id=1, domain_id=10, db=db)
            assert job.status == CrawlJobStatus.CANCELLED

    def test_cancel_running_job_sets_cancelled(self):
        db = MagicMock()
        job = self._make_job(CrawlJobStatus.RUNNING)

        with patch('services.crawl_job_service.CrawlJobRepository') as mock_repo:
            mock_repo.get_by_id.return_value = job
            mock_repo.update.return_value = job
            CrawlJobService.cancel(job_id=1, domain_id=10, db=db)
            assert job.status == CrawlJobStatus.CANCELLED

    def test_cancel_completed_job_raises_validation_error(self):
        db = MagicMock()
        job = self._make_job(CrawlJobStatus.COMPLETED)

        with patch('services.crawl_job_service.CrawlJobRepository') as mock_repo:
            mock_repo.get_by_id.return_value = job
            with pytest.raises(ValidationError):
                CrawlJobService.cancel(job_id=1, domain_id=10, db=db)

    def test_cancel_failed_job_raises_validation_error(self):
        db = MagicMock()
        job = self._make_job(CrawlJobStatus.FAILED)

        with patch('services.crawl_job_service.CrawlJobRepository') as mock_repo:
            mock_repo.get_by_id.return_value = job
            with pytest.raises(ValidationError):
                CrawlJobService.cancel(job_id=1, domain_id=10, db=db)

    def test_cancel_cancelled_job_raises_validation_error(self):
        db = MagicMock()
        job = self._make_job(CrawlJobStatus.CANCELLED)

        with patch('services.crawl_job_service.CrawlJobRepository') as mock_repo:
            mock_repo.get_by_id.return_value = job
            with pytest.raises(ValidationError):
                CrawlJobService.cancel(job_id=1, domain_id=10, db=db)

    def test_cancel_job_not_found_raises_validation_error(self):
        db = MagicMock()

        with patch('services.crawl_job_service.CrawlJobRepository') as mock_repo:
            mock_repo.get_by_id.return_value = None
            with pytest.raises(ValidationError):
                CrawlJobService.cancel(job_id=99, domain_id=10, db=db)
