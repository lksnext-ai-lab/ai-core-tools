from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from db.base_class import Base
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, Base):
    '''User model class constructor'''
    __tablename__ = 'User'
    user_id = Column(Integer, primary_key=True)
    email = Column(String(255))
    name = Column(String(255))
    create_date = Column(DateTime, default=datetime.now)
    
    # Relationships
    apps = relationship('App', back_populates='user', lazy=True)
    api_keys = relationship('APIKey', back_populates='user', lazy=True)
    subscriptions = relationship('Subscription', back_populates='user', lazy=True, order_by='Subscription.created_at.desc()')

    def get_id(self):
        return self.user_id
    
    @property
    def subscription(self):
        """Get user's most recent active subscription, or most recent subscription if none active"""
        from extensions import db
        from model.subscription import Subscription, SubscriptionStatus
        
        # First, try to get the most recent active subscription
        active_subscription = db.session.query(Subscription).filter(
            Subscription.user_id == self.user_id,
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        ).order_by(Subscription.created_at.desc()).first()
        
        if active_subscription and active_subscription.is_active:
            return active_subscription
        
        # If no active subscription, get the most recent subscription regardless of status
        most_recent = db.session.query(Subscription).filter(
            Subscription.user_id == self.user_id
        ).order_by(Subscription.created_at.desc()).first()
        
        return most_recent
    
    @property
    def current_plan(self):
        """Get user's current active plan"""
        current_subscription = self.subscription
        if current_subscription and current_subscription.is_active:
            return current_subscription.plan
        # Return free plan if no active subscription
        from model.subscription import Plan
        from extensions import db
        return db.session.query(Plan).filter_by(name='free').first()
    
    @property
    def can_create_agent(self):
        """Check if user can create more agents"""
        current_agent_count = len([app for app in self.apps if hasattr(app, 'agents')])
        return current_agent_count < self.current_plan.max_agents if self.current_plan.max_agents != -1 else True
    
    @property
    def can_create_domain(self):
        """Check if user can create more domains"""
        # You'll need to implement domain counting logic based on your domain model
        return True  # Placeholder
    
    def has_feature(self, feature_name):
        """Check if user has access to a specific feature"""
        plan = self.current_plan
        return getattr(plan, f'has_{feature_name}', False)