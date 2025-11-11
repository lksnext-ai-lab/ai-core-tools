from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from db.database import Base


class Conversation(Base):
    """
    Model for tracking user conversations with agents.
    
    Each conversation represents an independent chat session between a user and an agent.
    The conversation history is stored in PostgreSQL via LangGraph's checkpointer,
    using thread_id = f"thread_{agent_id}_{session_id}"
    where session_id = f"conv_{agent_id}_{conversation_id}"
    """
    __tablename__ = "Conversation"
    
    # Primary key
    conversation_id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    agent_id = Column(Integer, ForeignKey('Agent.agent_id'), nullable=False)
    user_id = Column(Integer, ForeignKey('User.user_id'), nullable=True)  # Null for API key users
    
    # Conversation metadata
    title = Column(String(255), nullable=True)  # User-defined or auto-generated title
    session_id = Column(String(255), nullable=False, unique=True)  # Format: conv_{agent_id}_{uuid}
    
    # Tracking fields
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_message = Column(Text, nullable=True)  # Preview of last message
    message_count = Column(Integer, default=0, nullable=False)  # Number of messages in conversation
    
    # User context (for API key users who don't have user_id)
    api_key_hash = Column(String(64), nullable=True)  # MD5 hash of API key for tracking
    
    # Relationships
    agent = relationship("Agent", backref="conversations")
    user = relationship("User", backref="conversations", foreign_keys=[user_id])
    
    def __repr__(self):
        return f"<Conversation {self.conversation_id}: Agent={self.agent_id}, User={self.user_id}, Title='{self.title}'>"
    
    def to_dict(self):
        """Convert conversation to dictionary"""
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

