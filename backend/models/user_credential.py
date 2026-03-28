from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class UserCredential(Base):
    """Email+password local auth data for a user (one per user)."""
    __tablename__ = 'user_credentials'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('User.user_id', ondelete='CASCADE'), nullable=False, unique=True)
    hashed_password = Column(String(255), nullable=False)
    verification_token = Column(String(512), nullable=True)
    verification_token_expiry = Column(DateTime, nullable=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    reset_token = Column(String(512), nullable=True)
    reset_token_expiry = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship('User', back_populates='credential')
