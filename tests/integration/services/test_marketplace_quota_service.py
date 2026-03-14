"""
Integration tests for MarketplaceQuotaService.

Tests the core functionality of quota tracking, checking, and exemptions.
Requires a real database session (integration tests).
"""
import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from models.marketplace_usage import MarketplaceUsage
from models.user import User
from services.marketplace_quota_service import MarketplaceQuotaService


def _make_user(db: Session, email: str = None) -> User:
    """Helper to create and persist a test user."""
    # Use a sequence-like approach with timestamp for uniqueness
    if email is None:
        import time
        email = f"quota_test_{int(time.time() * 1000)}@test.com"
    user = User(email=email, name="Test User")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.mark.integration
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
        user = _make_user(db)

        usage = MarketplaceQuotaService.get_current_month_usage(user.user_id, db)

        assert usage == 0

    def test_get_current_month_usage_with_record(self, db: Session):
        """Test that get_current_month_usage returns correct count when record exists"""
        user = _make_user(db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

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
        user = _make_user(db)

        new_count = MarketplaceQuotaService.increment_usage(user.user_id, db)

        assert new_count == 1
        assert (
            MarketplaceQuotaService.get_current_month_usage(user.user_id, db) == 1
        )

    def test_increment_usage_updates_existing_record(self, db: Session):
        """Test that increment_usage increments an existing record"""
        user = _make_user(db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        usage_record = MarketplaceUsage(
            user_id=user.user_id,
            year=year,
            month=month,
            call_count=3,
        )
        db.add(usage_record)
        db.commit()

        new_count = MarketplaceQuotaService.increment_usage(user.user_id, db)

        assert new_count == 4
        assert (
            MarketplaceQuotaService.get_current_month_usage(user.user_id, db) == 4
        )

    def test_increment_usage_sequential_increments(self, db: Session):
        """Test that sequential increments work correctly (atomic UPSERT)"""
        user = _make_user(db)

        for i in range(5):
            count = MarketplaceQuotaService.increment_usage(user.user_id, db)
            assert count == i + 1

        final_count = MarketplaceQuotaService.get_current_month_usage(user.user_id, db)
        assert final_count == 5

    def test_check_quota_exceeded_unlimited(self, db: Session):
        """Test that quota of 0 means unlimited (never exceeded)"""
        user = _make_user(db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        usage_record = MarketplaceUsage(
            user_id=user.user_id,
            year=year,
            month=month,
            call_count=1000,
        )
        db.add(usage_record)
        db.commit()

        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota=0
        )

        assert is_exceeded is False

    def test_check_quota_exceeded_under_limit(self, db: Session):
        """Test that quota is not exceeded when below limit"""
        user = _make_user(db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        usage_record = MarketplaceUsage(
            user_id=user.user_id, year=year, month=month, call_count=5
        )
        db.add(usage_record)
        db.commit()

        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota=10
        )

        assert is_exceeded is False

    def test_check_quota_exceeded_at_limit(self, db: Session):
        """Test that quota is exceeded when usage == quota"""
        user = _make_user(db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        usage_record = MarketplaceUsage(
            user_id=user.user_id, year=year, month=month, call_count=10
        )
        db.add(usage_record)
        db.commit()

        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota=10
        )

        assert is_exceeded is True

    def test_check_quota_exceeded_over_limit(self, db: Session):
        """Test that quota is exceeded when usage > quota"""
        user = _make_user(db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        usage_record = MarketplaceUsage(
            user_id=user.user_id, year=year, month=month, call_count=15
        )
        db.add(usage_record)
        db.commit()

        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota=10
        )

        assert is_exceeded is True

    def test_is_user_exempt_returns_bool(self, db: Session):
        """Test that is_user_exempt returns a boolean"""
        user = _make_user(db, email="regular_quota@example.com")

        is_exempt = MarketplaceQuotaService.is_user_exempt(user)

        # Should return bool; False for non-omniadmin in test env
        assert isinstance(is_exempt, bool)

    def test_reset_user_current_month_usage_success(self, db: Session):
        """Test that reset_user_current_month_usage sets count to 0"""
        user = _make_user(db)
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        usage_record = MarketplaceUsage(
            user_id=user.user_id, year=year, month=month, call_count=10
        )
        db.add(usage_record)
        db.commit()

        MarketplaceQuotaService.reset_user_current_month_usage(user.user_id, db)

        final_count = MarketplaceQuotaService.get_current_month_usage(user.user_id, db)
        assert final_count == 0

    def test_reset_user_current_month_usage_no_record(self, db: Session):
        """Test that reset raises ValueError when no record exists"""
        user = _make_user(db)

        with pytest.raises(ValueError):
            MarketplaceQuotaService.reset_user_current_month_usage(user.user_id, db)

    def test_increment_and_check_workflow(self, db: Session):
        """Test a realistic workflow: increment usage and check quota"""
        user = _make_user(db)
        quota = 5

        # Start: no usage — should not be exceeded
        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota
        )
        assert is_exceeded is False

        # Increment 3 times → still under quota
        for _ in range(3):
            MarketplaceQuotaService.increment_usage(user.user_id, db)

        is_exceeded = MarketplaceQuotaService.check_quota_exceeded(
            user.user_id, db, quota
        )
        assert is_exceeded is False

        # Increment 2 more → at quota
        for _ in range(2):
            MarketplaceQuotaService.increment_usage(user.user_id, db)

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
