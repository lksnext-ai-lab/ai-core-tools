from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from db.database import Base
from datetime import datetime


class TierConfig(Base):
    """System-level configuration of resource limits per subscription tier."""
    __tablename__ = 'tier_configs'

    id = Column(Integer, primary_key=True)
    tier = Column(String(50), nullable=False)
    resource_type = Column(String(100), nullable=False)
    limit_value = Column(Integer, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('tier', 'resource_type', name='uq_tier_resource'),
    )
