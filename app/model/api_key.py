from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from db.base_class import Base

class APIKey(Base):
    '''API Key model for App authentication'''
    __tablename__ = 'APIKey'
    
    key_id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, nullable=False)  # The actual API key
    name = Column(String(255), nullable=False)  # A friendly name for the key
    app_id = Column(Integer, ForeignKey('App.app_id'), nullable=False)
    user_id = Column(Integer, ForeignKey('User.user_id'), nullable=False)  # Owner of the key
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    app = relationship("App", back_populates="api_keys")
    user = relationship("User", back_populates="api_keys")