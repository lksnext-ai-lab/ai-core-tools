from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from models.usage_record import UsageRecord
from datetime import datetime, date
from utils.logger import get_logger

logger = get_logger(__name__)


def _current_period_start() -> date:
    """Return the first day of the current calendar month as the billing period start."""
    today = date.today()
    return today.replace(day=1)


class UsageRecordRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_current(self, user_id: int) -> Optional[UsageRecord]:
        """Return the current billing period UsageRecord for a user, or None."""
        period_start = _current_period_start()
        return (
            self.db.query(UsageRecord)
            .filter(UsageRecord.user_id == user_id, UsageRecord.billing_period_start == period_start)
            .first()
        )

    def _get_or_create_current(self, user_id: int) -> UsageRecord:
        """Get or create the current period record. Must be called within a transaction."""
        period_start = _current_period_start()
        record = (
            self.db.query(UsageRecord)
            .filter(UsageRecord.user_id == user_id, UsageRecord.billing_period_start == period_start)
            .with_for_update()
            .first()
        )
        if not record:
            record = UsageRecord(
                user_id=user_id,
                billing_period_start=period_start,
                call_count=0,
            )
            self.db.add(record)
            self.db.flush()
        return record

    def increment(self, user_id: int) -> UsageRecord:
        """Increment the system LLM call counter for the current period (race-condition-safe via SELECT FOR UPDATE)."""
        record = self._get_or_create_current(user_id)
        record.call_count += 1
        record.updated_at = datetime.utcnow()
        self.db.flush()
        return record

    def get_pct_used(self, user_id: int, limit: int) -> float:
        """Return fraction of quota used (0.0–1.0+). Returns 0.0 if limit is 0 or unlimited (-1)."""
        if limit <= 0:
            return 0.0
        record = self.get_current(user_id)
        if not record:
            return 0.0
        return record.call_count / limit

    def reset_period(self, user_id: int, new_period_start: date) -> UsageRecord:
        """Start a new billing period record (e.g., on invoice.paid)."""
        record = (
            self.db.query(UsageRecord)
            .filter(UsageRecord.user_id == user_id, UsageRecord.billing_period_start == new_period_start)
            .first()
        )
        if not record:
            record = UsageRecord(
                user_id=user_id,
                billing_period_start=new_period_start,
                call_count=0,
            )
            self.db.add(record)
        else:
            record.call_count = 0
            record.updated_at = datetime.utcnow()
        self.db.flush()
        return record
