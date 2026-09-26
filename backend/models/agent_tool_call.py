import uuid
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from db.database import Base
from models.enums.agent_tool_call_type import AgentToolCallType
from models.enums.agent_tool_call_status import AgentToolCallStatus


class AgentToolCall(Base):
    """Records a single tool call made during an agent execution."""
    __tablename__ = 'agent_tool_call'

    tool_call_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey('agent_execution_event.event_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    tool_name = Column(String(255), nullable=False)
    tool_type = Column(
        Enum(AgentToolCallType, name='agent_tool_call_type', create_type=False),
        nullable=False,
    )
    sub_agent_id = Column(
        Integer,
        ForeignKey('Agent.agent_id', ondelete='SET NULL'),
        nullable=True,
    )
    mcp_config_id = Column(
        Integer,
        ForeignKey('MCPConfig.config_id', ondelete='SET NULL'),
        nullable=True,
    )
    duration_ms = Column(Integer, nullable=True)
    status = Column(
        Enum(AgentToolCallStatus, name='agent_tool_call_status', create_type=False),
        nullable=False,
    )
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False)

    # Relationships
    event = relationship('AgentExecutionEvent', back_populates='tool_call_rows')
