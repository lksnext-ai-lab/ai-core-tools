from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime

class User(Base):
    '''User model class constructor'''
    __tablename__ = 'User'
    user_id = Column(Integer, primary_key=True)
    email = Column(String(255))
    name = Column(String(255))
    create_date = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    owned_apps = relationship('App', foreign_keys='App.owner_id', back_populates='owner', lazy=True)
    app_collaborations = relationship('AppCollaborator', foreign_keys='AppCollaborator.user_id', back_populates='user', lazy=True)
    api_keys = relationship('APIKey', back_populates='user', lazy=True)
    subscriptions = relationship('Subscription', back_populates='user', lazy=True)

    def get_id(self):
        return self.user_id
    
    @property
    def apps(self):
        """Get all apps user has access to (owned + collaborated)"""
        from services.user_service import UserService
        return UserService.get_user_accessible_apps(self.user_id)
    
    @property
    def subscription(self):
        """Get user's current active subscription (or most recent if none active)"""
        from services.user_service import UserService
        return UserService.get_user_subscription(self.user_id)
    
    @property
    def current_plan(self):
        """Get user's current active plan"""
        from services.user_service import UserService
        return UserService.get_user_current_plan(self.user_id)
    
    @property
    def can_create_agent(self):
        """Check if user can create more agents"""
        from services.user_service import UserService
        return UserService.can_user_create_agent(self.user_id)
    
    @property
    def can_create_domain(self):
        """Check if user can create more domains"""
        from services.user_service import UserService
        return UserService.can_user_create_domain(self.user_id)
    
    def has_feature(self, feature_name):
        """Check if user has access to a specific feature"""
        from services.user_service import UserService
        return UserService.user_has_feature(self.user_id, feature_name) 