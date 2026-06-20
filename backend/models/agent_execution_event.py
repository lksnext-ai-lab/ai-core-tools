import uuid
import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.database import Base
from models.enums.agent_execution_caller_type import AgentExecutionCallerType
from models.enums.agent_execution_status import AgentExecutionStatus


class AgentExecutionEvent(Base):
    """Records a single agent execution (one LLM invocation via _execute_agent_async)."""
    __tablename__ = 'agent_execution_event'

    event_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    app_id = Column(
        Integer,
        ForeignKey('App.app_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    agent_id = Column(
        Integer,
        ForeignKey('Agent.agent_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    conversation_id = Column(
        Integer,
        ForeignKey('Conversation.conversation_id', ondelete='SET NULL'),
        nullable=True,
    )
    user_id = Column(
        Integer,
        ForeignKey('User.user_id', ondelete='SET NULL'),
        nullable=True,
    )
    api_key_id = Column(
        Integer,
        ForeignKey('APIKey.key_id', ondelete='SET NULL'),
        nullable=True,
    )
    caller_type = Column(
        Enum(AgentExecutionCallerType, name='agent_execution_caller_type', create_type=False),
        nullable=False,
    )
    parent_execution_id = Column(
        UUID(as_uuid=True),
        ForeignKey('agent_execution_event.event_id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    status = Column(
        Enum(AgentExecutionStatus, name='agent_execution_status', create_type=False),
        nullable=False,
    )
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    model_name = Column(String(255), nullable=True)
    ai_service_id = Column(
        Integer,
        ForeignKey('AIService.service_id', ondelete='SET NULL'),
        nullable=True,
    )
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    tool_calls = Column(JSON, nullable=True)
    retrieved_docs = Column(JSON, nullable=True)
    had_files = Column(Boolean, nullable=False, server_default='false')
    file_count = Column(Integer, nullable=False, server_default='0')
    had_images = Column(Boolean, nullable=False, server_default='false')
    output_parser_used = Column(Boolean, nullable=False, server_default='false')
    parser_succeeded = Column(Boolean, nullable=True)
    prompt_chars = Column(Integer, nullable=True)
    response_chars = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    tool_call_rows = relationship(
        'AgentToolCall',
        back_populates='event',
        cascade='all, delete-orphan',
    )
    children = relationship(
        'AgentExecutionEvent',
        foreign_keys=[parent_execution_id],
        backref='parent_event',
        remote_side='AgentExecutionEvent.event_id',
    )
