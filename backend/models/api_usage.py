from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from db.base import Base

class APIUsage(Base):
    '''API Usage tracking model for subscription limits'''
    __tablename__ = 'APIUsage'
    
    usage_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('User.user_id'), nullable=False)
    subscription_id = Column(Integer, ForeignKey('Subscription.subscription_id'), nullable=False)
    
    # Time period tracking
    year = Column(Integer, nullable=False)  # 2024
    month = Column(Integer, nullable=False)  # 1-12
    
    # Usage counters
    api_calls_count = Column(Integer, default=0, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_user_year_month', 'user_id', 'year', 'month'),
        Index('idx_subscription_year_month', 'subscription_id', 'year', 'month'),
    )
    
    @classmethod
    def get_or_create_current_usage(cls, user_id: int, subscription_id: int):
        """Get or create API usage record for current month"""
        from extensions import db
        
        now = datetime.utcnow()
        current_year = now.year
        current_month = now.month
        
        usage = db.session.query(cls).filter_by(
            user_id=user_id,
            subscription_id=subscription_id,
            year=current_year,
            month=current_month
        ).first()
        
        if not usage:
            usage = cls(
                user_id=user_id,
                subscription_id=subscription_id,
                year=current_year,
                month=current_month,
                api_calls_count=0
            )
            db.session.add(usage)
            db.session.commit()
        
        return usage
    
    def increment_api_calls(self):
        """Atomically increment API calls counter"""
        from extensions import db
        
        self.api_calls_count += 1
        self.updated_at = datetime.utcnow()
        db.session.commit()
        return self.api_calls_count 