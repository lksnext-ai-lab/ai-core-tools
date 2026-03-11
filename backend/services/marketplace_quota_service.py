"""
Marketplace quota service for tracking and enforcing per-user monthly API call limits.
Handles quota checking, usage tracking, and admin exemptions.
"""
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from sqlalchemy.dialects.postgresql import insert

from models.marketplace_usage import MarketplaceUsage
from models.user import User
from utils.config import is_omniadmin
from utils.logger import get_logger

logger = get_logger(__name__)


class MarketplaceQuotaService:
    """
    Service for managing marketplace agent quotas on a per-user, per-month basis.
    All operations use UTC time for consistency.
    """

    @staticmethod
    def get_current_utc_month_year() -> tuple[int, int]:
        """
        Get current year and month in UTC.

        Returns:
            Tuple of (year, month) where month is 1-12
        """
        now_utc = datetime.utcnow()
        return now_utc.year, now_utc.month

    @staticmethod
    def get_current_month_usage(user_id: int, db: Session) -> int:
        """
        Get the call count for a user in the current UTC month.

        Args:
            user_id: The user ID
            db: Database session

        Returns:
            Call count for current month (0 if no record exists)
        """
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        usage = db.query(MarketplaceUsage).filter(
            and_(
                MarketplaceUsage.user_id == user_id,
                MarketplaceUsage.year == year,
                MarketplaceUsage.month == month,
            )
        ).first()

        if not usage:
            return 0

        return usage.call_count

    @staticmethod
    def increment_usage(user_id: int, db: Session) -> int:
        """
        Atomically increment the call count for a user in the current UTC month.

        Creates a new record if none exists, otherwise increments the existing one.
        Uses PostgreSQL UPSERT (INSERT ... ON CONFLICT DO UPDATE) for atomic operation.

        Args:
            user_id: The user ID
            db: Database session

        Returns:
            The new call count value after increment

        Raises:
            Exception: If database operation fails
        """
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        # Build the UPSERT query using SQLAlchemy's PostgreSQL dialect
        stmt = insert(MarketplaceUsage).values(
            user_id=user_id,
            year=year,
            month=month,
            call_count=1,
        ).on_conflict_do_update(
            index_elements=['user_id', 'year', 'month'],
            set_={'call_count': MarketplaceUsage.call_count + 1}
        )

        # Execute the UPSERT
        db.execute(stmt)
        db.commit()

        # Fetch and return the updated count
        updated_usage = db.query(MarketplaceUsage).filter(
            and_(
                MarketplaceUsage.user_id == user_id,
                MarketplaceUsage.year == year,
                MarketplaceUsage.month == month,
            )
        ).first()

        if not updated_usage:
            logger.error(
                f"Failed to increment marketplace usage for user {user_id}, "
                f"month {year}-{month:02d}"
            )
            raise RuntimeError("Failed to increment marketplace usage")

        logger.debug(
            f"Incremented marketplace usage for user {user_id}: "
            f"new count = {updated_usage.call_count}"
        )

        return updated_usage.call_count

    @staticmethod
    def check_quota_exceeded(user_id: int, db: Session, quota: int) -> bool:
        """
        Check if a user's current month usage exceeds the quota.

        Args:
            user_id: The user ID
            db: Database session
            quota: The quota limit (0 means unlimited)

        Returns:
            True if usage >= quota, False otherwise
            If quota is 0, returns False (unlimited allowed)
        """
        if quota <= 0:
            # Unlimited quota
            return False

        usage = MarketplaceQuotaService.get_current_month_usage(user_id, db)
        return usage >= quota

    @staticmethod
    def is_user_exempt(user: User) -> bool:
        """
        Check if a user is exempt from quota limits.

        A user is exempt if they have OMNIADMIN role.

        Args:
            user: User object

        Returns:
            True if user is OMNIADMIN, False otherwise
        """
        return is_omniadmin(user.email)

    @staticmethod
    def reset_user_current_month_usage(user_id: int, db: Session) -> None:
        """
        Reset the call count to 0 for a user in the current UTC month.

        Args:
            user_id: The user ID to reset
            db: Database session

        Raises:
            ValueError: If no record exists for the user in current month
        """
        year, month = MarketplaceQuotaService.get_current_utc_month_year()

        # Find the record
        usage = db.query(MarketplaceUsage).filter(
            and_(
                MarketplaceUsage.user_id == user_id,
                MarketplaceUsage.year == year,
                MarketplaceUsage.month == month,
            )
        ).first()

        if not usage:
            logger.warning(
                f"No marketplace usage record found for user {user_id}, "
                f"month {year}-{month:02d}"
            )
            raise ValueError(
                f"No usage record found for user {user_id} in {year}-{month:02d}"
            )

        # Reset the count
        usage.call_count = 0
        db.commit()

        logger.info(
            f"Reset marketplace usage for user {user_id}, month {year}-{month:02d}"
        )
