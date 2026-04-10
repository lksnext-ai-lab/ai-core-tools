from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from db.database import Base


class A2ATask(Base):
    """Persisted A2A task state linked to Mattin AI conversations."""

    __tablename__ = "A2ATask"

    task_id = Column(String(255), primary_key=True)
    context_id = Column(String(255), nullable=False, index=True)
    app_id = Column(Integer, ForeignKey("App.app_id"), nullable=False, index=True)
    agent_id = Column(Integer, ForeignKey("Agent.agent_id"), nullable=False, index=True)
    api_key_id = Column(
        Integer,
        ForeignKey("APIKey.key_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id = Column(Integer, ForeignKey("Conversation.conversation_id"), nullable=True, index=True)
    status = Column(String(64), nullable=False, default="submitted")
    task_payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)

    app = relationship("App")
    agent = relationship("Agent")
    api_key = relationship("APIKey")
    conversation = relationship("Conversation")
