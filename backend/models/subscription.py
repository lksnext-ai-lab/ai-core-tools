import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class SubscriptionTier(enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"


class BillingStatus(enum.Enum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    NONE = "none"


class Subscription(Base):
    """Subscription tier and billing state for a user (one per user)."""
    __tablename__ = 'subscriptions'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('User.user_id', ondelete='CASCADE'), nullable=False, unique=True)
    tier = Column(Enum(SubscriptionTier, values_callable=lambda x: [e.value for e in x]), nullable=False, default=SubscriptionTier.FREE)
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    billing_status = Column(Enum(BillingStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=BillingStatus.NONE)
    trial_end = Column(DateTime, nullable=True)
    admin_override_tier = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship('User', back_populates='subscription')
