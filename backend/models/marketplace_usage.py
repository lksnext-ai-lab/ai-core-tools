from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class MarketplaceUsage(Base):
    """
    Model for tracking monthly API call counts to marketplace agents per user.
    
    Each row represents a user's monthly usage (call count) for a specific month/year.
    The (user_id, year, month) tuple is unique to prevent duplicate month entries.
    """
    __tablename__ = 'MarketplaceUsage'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    user_id = Column(
        Integer,
        ForeignKey('User.user_id', ondelete='CASCADE'),
        nullable=False
    )
    
    # Year and month tracking (UTC based)
    year = Column(Integer, nullable=False)  # Calendar year (e.g., 2026)
    month = Column(Integer, nullable=False)  # Calendar month (1-12)
    
    # Usage tracking
    call_count = Column(Integer, default=0, nullable=False)  # Number of marketplace agent calls
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Unique constraint: one entry per user per month
    __table_args__ = (
        UniqueConstraint('user_id', 'year', 'month', name='uq_user_year_month'),
        Index('ix_user_id', 'user_id'),
        Index('ix_user_year_month', 'user_id', 'year', 'month'),
    )
    
    # Relationships
    user = relationship('User', backref='marketplace_usage')
    
    def __repr__(self):
        return f"<MarketplaceUsage user_id={self.user_id}, {self.year}-{self.month:02d}, calls={self.call_count}>"
