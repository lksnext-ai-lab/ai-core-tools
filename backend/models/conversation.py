import enum

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from db.database import Base


class ConversationSource(enum.Enum):
    PLAYGROUND = "playground"
    MARKETPLACE = "marketplace"
    API = "api"


class Conversation(Base):
    """Chat session. History lives in LangGraph's checkpointer under thread_id = f"thread_{agent_id}_{session_id}"."""
    __tablename__ = "Conversation"

    conversation_id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey('Agent.agent_id'), nullable=False)
    user_id = Column(Integer, ForeignKey('User.user_id', ondelete='SET NULL'), nullable=True)
    title = Column(String(255), nullable=True)
    session_id = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_message = Column(Text, nullable=True)
    message_count = Column(Integer, default=0, nullable=False)
    api_key_hash = Column(String(64), nullable=True)  # MD5 hash of the API key; user_id is null for API-key requests

    source = Column(
        Enum(ConversationSource),
        nullable=False,
        default=ConversationSource.PLAYGROUND
    )

    # Sandbox session tracking (IT-1 / Q5): provider sandbox id for reconnect attempts after a restart.
    sandbox_session_id = Column(String(255), nullable=True)
    # Serialized JSON snapshot of the sandbox state (provider, session_key, sandbox_id, updated_at).
    sandbox_state = Column(Text, nullable=True)

    agent = relationship("Agent", backref="conversations")
    user = relationship("User", backref="conversations", foreign_keys=[user_id])
    
    def __repr__(self):
        return f"<Conversation {self.conversation_id}: Agent={self.agent_id}, User={self.user_id}, Title='{self.title}'>"
    
    def to_dict(self):
        return {
            "conversation_id": self.conversation_id,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "title": self.title,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_message": self.last_message,
            "message_count": self.message_count
        }

