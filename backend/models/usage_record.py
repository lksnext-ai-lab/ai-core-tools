from sqlalchemy import Column, Integer, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class UsageRecord(Base):
    """System LLM call count per user per billing period."""
    __tablename__ = 'usage_records'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('User.user_id', ondelete='CASCADE'), nullable=False)
    billing_period_start = Column(Date, nullable=False)
    call_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship('User')

    __table_args__ = (
        UniqueConstraint('user_id', 'billing_period_start', name='uq_usage_user_period'),
    )
