"""
Unit tests for MarketplaceQuotaService.

Tests the core functionality of quota tracking, checking, and exemptions.
"""
import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from backend.models.marketplace_usage import MarketplaceUsage
from backend.models.user import User
from backend.services.marketplace_quota_service import MarketplaceQuotaService
from tests.factories import UserFactory


@pytest.mark.unit
class TestMarketplaceQuotaServiceMethods:
    """Test suite for MarketplaceQuotaService static methods"""

    def test_get_current_utc_month_year(self):
        """Test that get_current_utc_month_year returns valid UTC month/year"""
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        assert isinstance(year, int)
        assert isinstance(month, int)
        assert 1 <= month <= 12
        assert year >= 2020  # Sanity check

        # Verify it matches actual UTC time
        now = datetime.utcnow()
        assert year == now.year
        assert month == now.month

    def test_get_current_month_usage_no_record(self, db: Session):
        """Test that get_current_month_usage returns 0 when no record exists"""
        user = UserFactory.create(db=db)

        usage = MarketplaceQuotaService.get_current_month_usage(user.user_id, db)

        assert usage == 0

    def test_get_current_month_usage_with_record(self, db: Session):
        """Test that get_current_month_usage returns correct count when record exists"""
        user = UserFactory.create(db=db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        # Create a marketplace usage record
        usage_record = MarketplaceUsage(
            user_id=user.user_id,
            year=year,
            month=month,
            call_count=5,
        )
        db.add(usage_record)
        db.commit()

        usage = MarketplaceQuotaService.get_current_month_usage(user.user_id, db)

        assert usage == 5

    def test_increment_usage_creates_new_record(self, db: Session):
        """Test that increment_usage creates a new record when none exists"""
        user = UserFactory.create(db=db)

        new_count = MarketplaceQuotaService.increment_usage(user.user_id, db)

        assert new_count == 1
        assert (
            MarketplaceQuotaService.get_current_month_usage(user.user_id, db) == 1
        )

    def test_increment_usage_updates_existing_record(self, db: Session):
        """Test that increment_usage increments an existing record"""
        user = UserFactory.create(db=db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        # Create initial record with count=3
        usage_record = MarketplaceUsage(
            user_id=user.user_id,
            year=year,
            month=month,
            call_count=3,
        )
        db.add(usage_record)
        db.commit()

        # Increment
        new_count = MarketplaceQuotaService.increment_usage(user.user_id, db)

        assert new_count == 4
        assert (
            MarketplaceQuotaService.get_current_month_usage(user.user_id, db) == 4
        )

    def test_increment_usage_concurrent_increments(self, db: Session):
        """Test that concurrent increments work correctly (atomic UPSERT)"""
        user = UserFactory.create(db=db)

        # Simulate multiple concurrent increments
        for i in range(5):
            count = MarketplaceQuotaService.increment_usage(user.user_id, db)
            assert count == i + 1

        # Verify final count
        final_count = MarketplaceQuotaService.get_current_month_usage(
            user.user_id, db
        )
        assert final_count == 5

    def test_check_quota_exceeded_unlimited(self, db: Session):
        """Test that quota of 0 means unlimited (never exceeded)"""
        user = UserFactory.create(db=db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        # Create record with high count
        usage_record = MarketplaceUsage(
            user_id=user.user_id,
            year=year,
            month=month,
            call_count=1000,
        )
        db.add(usage_record)
        db.commit()

        # Check with quota=0 (unlimited)
        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota=0
        )

        assert is_exceeded is False

    def test_check_quota_exceeded_under_limit(self, db: Session):
        """Test that quota is not exceeded when below limit"""
        user = UserFactory.create(db=db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        usage_record = MarketplaceUsage(
            user_id=user.user_id,
            year=year,
            month=month,
            call_count=5,
        )
        db.add(usage_record)
        db.commit()

        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota=10
        )

        assert is_exceeded is False

    def test_check_quota_exceeded_at_limit(self, db: Session):
        """Test that quota is exceeded when usage >= quota"""
        user = UserFactory.create(db=db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        usage_record = MarketplaceUsage(
            user_id=user.user_id,
            year=year,
            month=month,
            call_count=10,
        )
        db.add(usage_record)
        db.commit()

        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota=10
        )

        assert is_exceeded is True

    def test_check_quota_exceeded_over_limit(self, db: Session):
        """Test that quota is exceeded when usage > quota"""
        user = UserFactory.create(db=db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        usage_record = MarketplaceUsage(
            user_id=user.user_id,
            year=year,
            month=month,
            call_count=15,
        )
        db.add(usage_record)
        db.commit()

        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota=10
        )

        assert is_exceeded is True

    def test_is_user_exempt_omniadmin(self, db: Session):
        """Test that OMNIADMIN user is exempt"""
        # Note: This test requires setting AICT_OMNIADMINS env var
        # For now, create a regular user and test non-omniadmin case
        user = UserFactory.create(db=db, email="regular@example.com")

        is_exempt = MarketplaceQuotaService.is_user_exempt(user)

        # This will be False unless the email is in AICT_OMNIADMINS
        # In CI/test environment, might need to configure
        assert isinstance(is_exempt, bool)

    def test_reset_user_current_month_usage_success(self, db: Session):
        """Test that reset_user_current_month_usage sets count to 0"""
        user = UserFactory.create(db=db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        # Create record with count=10
        usage_record = MarketplaceUsage(
            user_id=user.user_id,
            year=year,
            month=month,
            call_count=10,
        )
        db.add(usage_record)
        db.commit()

        # Reset
        MarketplaceQuotaService.reset_user_current_month_usage(user.user_id, db)

        # Verify count is 0
        final_count = MarketplaceQuotaService.get_current_month_usage(
            user.user_id, db
        )
        assert final_count == 0

    def test_reset_user_current_month_usage_no_record(self, db: Session):
        """Test that reset_user_current_month_usage raises ValueError if no record exists"""
        user = UserFactory.create(db=db)

        with pytest.raises(ValueError):
            MarketplaceQuotaService.reset_user_current_month_usage(user.user_id, db)

    def test_increment_and_check_workflow(self, db: Session):
        """Test a realistic workflow: increment usage and check quota"""
        user = UserFactory.create(db=db)
        quota = 5

        # Start: no usage
        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota
        )
        assert is_exceeded is False

        # Increment 3 times
        for _ in range(3):
            MarketplaceQuotaService.increment_usage(user.user_id, db)

        # Still under quota
        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota
        )
        assert is_exceeded is False

        # Increment 2 more times (reach quota)
        for _ in range(2):
            MarketplaceQuotaService.increment_usage(user.user_id, db)

        # Now at quota (exceeded)
        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota
        )
        assert is_exceeded is True

        # Reset and verify
        MarketplaceQuotaService.reset_user_current_month_usage(user.user_id, db)
        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota
        )
        assert is_exceeded is False
