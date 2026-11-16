"""Tables backing the flexible per-App Chat (internal chat agent).

No ORM relationships to App/User/Conversation: deletion is handled by the DB
foreign keys (ON DELETE CASCADE / SET NULL), so the ORM never tries to NULL
these rows. Snapshot columns (ai_service_id, silo_id, ...) deliberately have no
FK so a turn's history survives deletion of the service/silo it used.
"""

from datetime import datetime

from sqlalchemy import (
    JSON, BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID

from db.database import Base


class ConversationTurn(Base):
    """Per-turn snapshot of the effective configuration used for an assistant message."""
    __tablename__ = 'conversation_turn'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(
        Integer, ForeignKey('Conversation.conversation_id', ondelete='CASCADE'), nullable=False
    )
    app_id = Column(Integer, ForeignKey('App.app_id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('User.user_id', ondelete='SET NULL'), nullable=True)
    turn_index = Column(Integer, nullable=False)
    assistant_message_id = Column(String(128), nullable=True)
    execution_event_id = Column(UUID(as_uuid=True), nullable=True)
    ai_service_id = Column(Integer, nullable=True)
    ai_service_name = Column(String(255), nullable=False)
    ai_model_name = Column(String(255), nullable=True)
    silo_id = Column(Integer, nullable=True)
    silo_name = Column(String(255), nullable=True)
    silo_source_type = Column(String(32), nullable=True)
    skills = Column(JSON, nullable=False, default=list, server_default='[]')
    mcp_configs = Column(JSON, nullable=False, default=list, server_default='[]')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('conversation_id', 'turn_index', name='uq_conversation_turn_conversation_index'),
        Index('ix_conversation_turn_app_id', 'app_id'),
        Index('ix_conversation_turn_user_id', 'user_id', postgresql_where=text('user_id IS NOT NULL')),
    )


class ChatUserDefault(Base):
    """Last selection a user made in an App's Chat (one row per user+App)."""
    __tablename__ = 'chat_user_default'

    user_id = Column(Integer, ForeignKey('User.user_id', ondelete='CASCADE'), primary_key=True)
    app_id = Column(Integer, ForeignKey('App.app_id', ondelete='CASCADE'), primary_key=True)
    selection = Column(JSON, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # PK is (user_id, app_id): app_id-only cascades from App deletion need their own index.
    __table_args__ = (Index('ix_chat_user_default_app_id', 'app_id'),)


class ChatConversationState(Base):
    """Current selection of a Chat conversation (config of the last completed turn)."""
    __tablename__ = 'chat_conversation_state'

    conversation_id = Column(
        Integer, ForeignKey('Conversation.conversation_id', ondelete='CASCADE'), primary_key=True
    )
    app_id = Column(Integer, ForeignKey('App.app_id', ondelete='CASCADE'), nullable=False)
    selection = Column(JSON, nullable=False)
    # Bumped by every reset of the conversation (under FOR UPDATE on this row). A turn that
    # captured an older value when it started must not persist anything when it completes.
    generation = Column(Integer, nullable=False, default=0, server_default='0')
    # Compare-and-set "turn in flight" marker: a turn claims the row by setting a fresh
    # busy_token and busy_until (expiry, so a crashed turn cannot block forever); a second
    # turn finding an unexpired marker is rejected with 409. Rows are addressed by PK: no index.
    busy_token = Column(UUID(as_uuid=True), nullable=True)
    busy_until = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index('ix_chat_conversation_state_app_id', 'app_id'),)
