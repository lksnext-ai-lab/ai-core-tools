"""Usage tracking service: increment/query system LLM call counters."""
from datetime import date
from sqlalchemy.orm import Session

from deployment_mode import is_self_managed
from models.usage_record import UsageRecord
from repositories.usage_record_repository import UsageRecordRepository
from repositories.subscription_repository import SubscriptionRepository
from repositories.tier_config_repository import TierConfigRepository
from schemas.usage_schemas import UsageRead
from utils.logger import get_logger

logger = get_logger(__name__)

_WARNING_THRESHOLD = 0.80  # 80%
# Track per-user per-period warning sends to avoid spamming
_warned_users: dict = {}  # In-process cache; lightweight enough for per-period tracking


def _get_effective_tier(db: Session, user_id: int) -> str:
    sub_repo = SubscriptionRepository(db)
    sub = sub_repo.get_by_user_id(user_id)
    if not sub:
        return "free"
    if sub.admin_override_tier:
        return sub.admin_override_tier
    return sub.tier.value if sub.tier else "free"


class UsageTrackingService:

    @staticmethod
    def record_system_llm_call(db: Session, user_id: int) -> UsageRecord:
        """Increment the system LLM call counter.

        After incrementing, checks if usage has crossed the 80% threshold and sends
        a warning email once per period.
        Returns the updated UsageRecord.
        Is a no-op in self-managed mode.
        """
        if is_self_managed():
            return None

        usage_repo = UsageRecordRepository(db)
        record = usage_repo.increment(user_id)

        # Check 80% warning threshold
        tier = _get_effective_tier(db, user_id)
        tier_repo = TierConfigRepository(db)
        limit = tier_repo.get_limit(tier, "llm_calls")

        if limit > 0:
            pct = record.call_count / limit
            period_key = f"{user_id}:{record.billing_period_start}"
            already_warned = _warned_users.get(period_key, False)

            if pct >= _WARNING_THRESHOLD and not already_warned:
                _warned_users[period_key] = True
                try:
                    from repositories.user_repository import UserRepository
                    from services.email_service import EmailService
                    user = UserRepository(db).get_by_id(user_id)
                    if user:
                        EmailService.send_quota_warning_email(to=user.email, pct=pct)
                except Exception as exc:
                    logger.warning("Failed to send quota warning email: %s", exc)

        return record

    @staticmethod
    def get_usage(db: Session, user_id: int) -> UsageRead:
        """Return current usage summary for a user."""
        if is_self_managed():
            return UsageRead(call_count=0, call_limit=0, pct_used=0.0)

        usage_repo = UsageRecordRepository(db)
        tier_repo = TierConfigRepository(db)
        tier = _get_effective_tier(db, user_id)
        limit = tier_repo.get_limit(tier, "llm_calls")

        record = usage_repo.get_current(user_id)
        call_count = record.call_count if record else 0
        period_start = record.billing_period_start if record else date.today().replace(day=1)
        pct = (call_count / limit) if limit > 0 else 0.0

        return UsageRead(
            call_count=call_count,
            call_limit=limit,
            period_start=period_start,
            pct_used=pct,
        )

    @staticmethod
    def reset_period(db: Session, user_id: int, period_start: date) -> UsageRecord:
        """Reset (or create) a usage record for a new billing period."""
        if is_self_managed():
            return None
        usage_repo = UsageRecordRepository(db)
        return usage_repo.reset_period(user_id, period_start)
