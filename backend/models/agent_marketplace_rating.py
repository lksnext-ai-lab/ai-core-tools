from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class AgentMarketplaceRating(Base):
    """
    One rating per user per marketplace agent profile (1–5 stars).
    Users may only rate agents they have had at least one marketplace
    conversation with.
    """
    __tablename__ = 'AgentMarketplaceRating'

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(
        Integer,
        ForeignKey('AgentMarketplaceProfile.id', ondelete='CASCADE'),
        nullable=False
    )
    user_id = Column(
        Integer,
        ForeignKey('User.user_id', ondelete='CASCADE'),
        nullable=False
    )
    rating = Column(Integer, nullable=False)  # 1–5

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('profile_id', 'user_id', name='uq_marketplace_rating_profile_user'),
    )

    # Relationships
    profile = relationship('AgentMarketplaceProfile', back_populates='ratings')
    user = relationship('User')

    def __repr__(self):
        return f"<AgentMarketplaceRating(id={self.id}, profile_id={self.profile_id}, user_id={self.user_id}, rating={self.rating})>"
