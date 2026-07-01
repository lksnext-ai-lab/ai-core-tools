import enum
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class PlatformRole(str, enum.Enum):
    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"


class User(Base):
    __tablename__ = 'User'
    user_id = Column(Integer, primary_key=True)
    email = Column(String(255))
    name = Column(String(255))
    create_date = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True, nullable=False)
    auth_method = Column(String(50), default='oidc', nullable=True)
    email_verified = Column(Boolean, default=True, nullable=False)
    platform_role = Column(String(50), default=PlatformRole.VIEWER.value, nullable=False)

    # passive_deletes=True on owned_apps/api_keys/app_collaborations (NO ACTION FKs):
    # UserService.delete_user empties these before db.delete(user), so ORM must not
    # emit SET NULL itself. On subscription (CASCADE FK) it lets the DB cascade run.
    owned_apps = relationship('App', foreign_keys='App.owner_id', back_populates='owner', lazy=True,
                              passive_deletes=True)
    app_collaborations = relationship('AppCollaborator', foreign_keys='AppCollaborator.user_id', back_populates='user', lazy=True,
                                      passive_deletes=True)
    api_keys = relationship('APIKey', back_populates='user', lazy=True,
                            passive_deletes=True)
    subscription = relationship('Subscription', back_populates='user', uselist=False, lazy=True,
                                cascade='all, delete-orphan', passive_deletes=True)
    credential = relationship('UserCredential', back_populates='user', uselist=False, lazy=True,
                              cascade='all, delete-orphan', passive_deletes=True)
    refresh_tokens = relationship('RefreshToken', back_populates='user', lazy=True,
                                  cascade='all, delete-orphan', passive_deletes=True)

    def get_id(self):
        return self.user_id
    
    @property
    def apps(self):
        from services.user_service import UserService
        return UserService.get_user_accessible_apps(self.user_id) 