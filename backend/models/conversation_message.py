from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    DateTime,
)
from sqlalchemy.sql import func

from db.database import Base

class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True)

    conversation_id = Column(
        Integer,
        ForeignKey("Conversation.conversation_id"),
        nullable=False
    )

    role = Column(String(20), nullable=False)

    message_type = Column(
        String(20),
        nullable=False,
        default="text"
    )

    content = Column(Text)

    audio_file_id = Column(String(255))

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )