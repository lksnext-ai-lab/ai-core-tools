from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from db.database import Base
from datetime import datetime


class SystemAIService(Base):
    """Platform-level AI Service configuration managed by OMNIADMIN.
    Not scoped to any App — available to all users based on their tier.
    """
    __tablename__ = 'system_ai_services'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    provider = Column(String(100), nullable=False)
    model = Column(String(255), nullable=False)
    api_key_encrypted = Column(Text, nullable=True)  # Write-only: excluded from Read schemas
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
