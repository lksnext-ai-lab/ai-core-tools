from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from db.database import Base


class A2AAgent(Base):
    """A2A-specific extension record for imported external agents."""

    __tablename__ = "A2AAgent"

    agent_id = Column(
        Integer,
        ForeignKey("Agent.agent_id", ondelete="CASCADE"),
        primary_key=True,
    )
    card_url = Column(String(2048), nullable=False)
    remote_agent_id = Column(String(512), nullable=True)
    remote_skill_id = Column(String(255), nullable=False)
    remote_skill_name = Column(String(255), nullable=False)
    remote_agent_metadata = Column(JSON, nullable=False, default=dict)
    remote_skill_metadata = Column(JSON, nullable=False, default=dict)
    sync_status = Column(String(32), nullable=False, default="synced")
    health_status = Column(String(32), nullable=False, default="healthy")
    last_successful_refresh_at = Column(DateTime, nullable=True)
    last_refresh_attempt_at = Column(DateTime, nullable=True)
    last_refresh_error = Column(Text, nullable=True)
    documentation_url = Column(String(2048), nullable=True)
    icon_url = Column(String(2048), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    agent = relationship("Agent", back_populates="a2a_config")
