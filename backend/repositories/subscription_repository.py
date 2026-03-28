from typing import Optional
from sqlalchemy.orm import Session
from models.subscription import Subscription, SubscriptionTier, BillingStatus
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)


class SubscriptionRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_by_user_id(self, user_id: int) -> Optional[Subscription]:
        """Return the subscription for a user, or None if not found."""
        return self.db.query(Subscription).filter(Subscription.user_id == user_id).first()

    def create(self, user_id: int, tier: SubscriptionTier = SubscriptionTier.FREE) -> Subscription:
        """Create a new subscription record for a user (typically Free tier on registration)."""
        sub = Subscription(
            user_id=user_id,
            tier=tier,
            billing_status=BillingStatus.NONE,
        )
        self.db.add(sub)
        self.db.flush()
        return sub

    def update_tier(
        self,
        user_id: int,
        tier: SubscriptionTier,
        billing_status: BillingStatus,
        stripe_customer_id: Optional[str] = None,
        stripe_subscription_id: Optional[str] = None,
        trial_end: Optional[datetime] = None,
    ) -> Optional[Subscription]:
        """Update subscription fields after a Stripe event or tier change."""
        sub = self.get_by_user_id(user_id)
        if not sub:
            return None
        sub.tier = tier
        sub.billing_status = billing_status
        if stripe_customer_id is not None:
            sub.stripe_customer_id = stripe_customer_id
        if stripe_subscription_id is not None:
            sub.stripe_subscription_id = stripe_subscription_id
        if trial_end is not None:
            sub.trial_end = trial_end
        sub.updated_at = datetime.utcnow()
        self.db.flush()
        return sub

    def set_admin_override(self, user_id: int, tier: str) -> Optional[Subscription]:
        """Set the OMNIADMIN manual tier override (tracked separately from Stripe state)."""
        sub = self.get_by_user_id(user_id)
        if not sub:
            return None
        sub.admin_override_tier = tier
        sub.updated_at = datetime.utcnow()
        self.db.flush()
        return sub
