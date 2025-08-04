from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime, desc
from sqlalchemy.orm import relationship
from db.base_class import Base
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, Base):
    '''User model class constructor'''
    __tablename__ = 'User'
    user_id = Column(Integer, primary_key=True)
    email = Column(String(255))
    name = Column(String(255))
    password_hash = Column(String(255))  # Para usuarios con contraseña
    is_google_user = Column(Boolean, default=False)  # Para distinguir tipo de usuario
    create_date = Column(DateTime, default=datetime.now)
    
    # Relationships
    owned_apps = relationship('App', foreign_keys='App.owner_id', back_populates='owner', lazy=True)
    app_collaborations = relationship('AppCollaborator', foreign_keys='AppCollaborator.user_id', back_populates='user', lazy=True)
    api_keys = relationship('APIKey', back_populates='user', lazy=True)
    subscriptions = relationship('Subscription', back_populates='user', lazy=True)

    def get_id(self):
        return self.user_id
    
    def set_password(self, password):
        """Set password hash for email/password authentication"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password for email/password authentication"""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
    
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