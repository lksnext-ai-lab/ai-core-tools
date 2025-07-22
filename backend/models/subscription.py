from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Enum, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from db.base import Base
import enum

class PlanType(enum.Enum):
    FREE = "free"
    STARTER = "starter"
    ENTERPRISE = "enterprise"

class SubscriptionStatus(enum.Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"

class Plan(Base):
    '''Pricing plan model'''
    __tablename__ = 'Plan'
    
    plan_id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)  # free, starter, enterprise
    display_name = Column(String(100), nullable=False)  # Free, Starter, Enterprise
    price = Column(Numeric(10, 2), nullable=False, default=0.00)
    billing_period = Column(String(20), default='monthly')  # monthly, yearly
    
    # Feature limits
    max_agents = Column(Integer, default=2)
    max_storage_gb = Column(Integer, default=1)  # Storage in GB
    max_domains = Column(Integer, default=1)
    max_api_calls_per_month = Column(Integer, default=1000)
    
    # Feature flags
    has_priority_support = Column(Boolean, default=False)
    has_advanced_analytics = Column(Boolean, default=False)
    has_team_collaboration = Column(Boolean, default=False)
    has_custom_integrations = Column(Boolean, default=False)
    has_on_premise = Column(Boolean, default=False)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    subscriptions = relationship('Subscription', back_populates='plan')

class Subscription(Base):
    '''User subscription model'''
    __tablename__ = 'Subscription'
    
    subscription_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('User.user_id'), nullable=False)
    plan_id = Column(Integer, ForeignKey('Plan.plan_id'), nullable=False)
    
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)
    started_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    
    # Trial information
    is_trial = Column(Boolean, default=False)
    trial_ends_at = Column(DateTime)
    
    # Billing information
    stripe_subscription_id = Column(String(255))  # For future Stripe integration
    last_payment_at = Column(DateTime)
    next_payment_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship('User', back_populates='subscriptions')
    plan = relationship('Plan', back_populates='subscriptions')
    
    @property
    def is_active(self):
        """Check if subscription is currently active"""
        if self.status == SubscriptionStatus.CANCELLED:
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        return True
    
    @property
    def is_trial_active(self):
        """Check if trial is currently active"""
        if not self.is_trial:
            return False
        if self.trial_ends_at and self.trial_ends_at < datetime.utcnow():
            return False
        return True
    
    @property
    def days_until_expiry(self):
        """Get days until subscription expires"""
        if not self.expires_at:
            return None
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days) 