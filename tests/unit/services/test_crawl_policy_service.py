"""Unit tests for CrawlPolicyService."""
import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError as PydanticValidationError

from schemas.crawl_schemas import CrawlPolicySchema
from services.crawl_policy_service import CrawlPolicyService
from utils.error_handlers import ValidationError


class TestCrawlPolicySchemaValidation:
    """Test Pydantic-level validation on CrawlPolicySchema."""

    def test_max_depth_over_limit_raises(self):
        with pytest.raises(PydanticValidationError):
            CrawlPolicySchema(max_depth=6, seed_url='https://example.com')

    def test_max_depth_at_limit_ok(self):
        schema = CrawlPolicySchema(max_depth=5, seed_url='https://example.com')
        assert schema.max_depth == 5

    def test_max_depth_zero_ok(self):
        schema = CrawlPolicySchema(max_depth=0, seed_url='https://example.com')
        assert schema.max_depth == 0

    def test_rate_limit_rps_zero_raises(self):
        with pytest.raises(PydanticValidationError):
            CrawlPolicySchema(rate_limit_rps=0, seed_url='https://example.com')

    def test_refresh_interval_too_large_raises(self):
        with pytest.raises(PydanticValidationError):
            CrawlPolicySchema(refresh_interval_hours=721, seed_url='https://example.com')


class TestCrawlPolicyServiceUpsert:
    """Test CrawlPolicyService.upsert_policy business rule validation."""

    def _make_db(self):
        db = MagicMock()
        return db

    def test_no_discovery_source_raises_validation_error(self):
        """upsert_policy with no seed_url, sitemap_url, or manual_urls raises ValidationError."""
        schema = CrawlPolicySchema(
            seed_url=None,
            sitemap_url=None,
            manual_urls=[],
        )
        db = self._make_db()

        with patch('services.crawl_policy_service.CrawlPolicyRepository') as mock_repo:
            mock_repo.get_by_domain.return_value = None
            with pytest.raises(ValidationError):
                CrawlPolicyService.upsert_policy(1, schema, db)

    def test_valid_seed_url_passes(self):
        """upsert_policy with seed_url proceeds to repository call."""
        schema = CrawlPolicySchema(seed_url='https://example.com')
        db = self._make_db()

        mock_policy = MagicMock()
        with patch('services.crawl_policy_service.CrawlPolicyRepository') as mock_repo:
            mock_repo.get_by_domain.return_value = None
            mock_repo.create.return_value = mock_policy
            result = CrawlPolicyService.upsert_policy(1, schema, db)
            assert mock_repo.create.called

    def test_valid_sitemap_url_passes(self):
        schema = CrawlPolicySchema(sitemap_url='https://example.com/sitemap.xml')
        db = self._make_db()

        mock_policy = MagicMock()
        with patch('services.crawl_policy_service.CrawlPolicyRepository') as mock_repo:
            mock_repo.get_by_domain.return_value = None
            mock_repo.create.return_value = mock_policy
            CrawlPolicyService.upsert_policy(1, schema, db)
            assert mock_repo.create.called

    def test_valid_manual_urls_passes(self):
        schema = CrawlPolicySchema(manual_urls=['https://example.com/page1'])
        db = self._make_db()

        mock_policy = MagicMock()
        with patch('services.crawl_policy_service.CrawlPolicyRepository') as mock_repo:
            mock_repo.get_by_domain.return_value = None
            mock_repo.create.return_value = mock_policy
            CrawlPolicyService.upsert_policy(1, schema, db)
            assert mock_repo.create.called

    def test_existing_policy_updates_not_creates(self):
        schema = CrawlPolicySchema(seed_url='https://example.com')
        db = self._make_db()

        existing = MagicMock()
        with patch('services.crawl_policy_service.CrawlPolicyRepository') as mock_repo:
            mock_repo.get_by_domain.return_value = existing
            mock_repo.update.return_value = existing
            CrawlPolicyService.upsert_policy(1, schema, db)
            assert mock_repo.update.called
            assert not mock_repo.create.called
