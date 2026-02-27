from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class AgentMarketplaceProfile(Base):
    """
    1:1 marketplace profile for an Agent.
    
    Stores presentation metadata used when an agent is published
    to the marketplace (display name, descriptions, category, tags, images).
    """
    __tablename__ = 'AgentMarketplaceProfile'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(
        Integer,
        ForeignKey('Agent.agent_id', ondelete='CASCADE'),
        unique=True,
        nullable=False
    )

    display_name = Column(String(255), nullable=True)
    short_description = Column(String(200), nullable=True)
    long_description = Column(Text, nullable=True)  # Markdown
    category = Column(String(50), nullable=True)
    tags = Column(JSON, nullable=True)  # Array of strings, max 5 enforced at service/schema level
    icon_url = Column(String(500), nullable=True)
    cover_image_url = Column(String(500), nullable=True)

    published_at = Column(DateTime, nullable=True)  # Set when first published
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    agent = relationship(
        'Agent',
        back_populates='marketplace_profile',
        uselist=False
    )

    def __repr__(self):
        return f"<AgentMarketplaceProfile(id={self.id}, agent_id={self.agent_id}, display_name='{self.display_name}')>"
