import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import relationship

from db.database import Base


class ApprovalStatus(str, enum.Enum):
    """Lifecycle of a human-in-the-loop approval request."""
    PENDING = "pending"
    DECIDING = "deciding"      # a decision was claimed and the run is resuming
    EXPIRING = "expiring"      # the sweeper claimed it and is resolving it as rejected
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


OPEN_APPROVAL_STATUSES = (ApprovalStatus.PENDING, ApprovalStatus.DECIDING, ApprovalStatus.EXPIRING)


class ApprovalChannel(str, enum.Enum):
    PLAYGROUND = "playground"
    MARKETPLACE = "marketplace"
    PUBLIC_API = "public_api"
    INTERNAL_SYNC = "internal_sync"
    PLATFORM_CHATBOT = "platform_chatbot"
    OPENAI_COMPAT = "openai_compat"
    MCP = "mcp"
    SCHEDULED = "scheduled"


INTERACTIVE_CHANNELS = (ApprovalChannel.PLAYGROUND, ApprovalChannel.MARKETPLACE, ApprovalChannel.PUBLIC_API)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HITLApproval(Base):
    """A pause of an agent run waiting for a human decision on one or more tool calls.

    The LangGraph checkpointer holds the paused graph; this row holds who may answer,
    until when, and what was decided.
    """
    __tablename__ = 'hitl_approval'

    id = Column(String(36), primary_key=True)
    app_id = Column(Integer, ForeignKey('App.app_id', ondelete='CASCADE'), nullable=False, index=True)
    agent_id = Column(Integer, ForeignKey('Agent.agent_id', ondelete='CASCADE'), nullable=False, index=True)
    conversation_id = Column(
        Integer, ForeignKey('Conversation.conversation_id', ondelete='CASCADE'), nullable=False, index=True
    )
    thread_id = Column(String(255), nullable=False)
    interrupt_id = Column(String(64), nullable=False)
    channel = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default=ApprovalStatus.PENDING.value)
    # [{action_id, name, args, description, allowed_decisions, args_schema?}] in LangChain's order
    actions = Column(JSON, nullable=False)
    decisions = Column(JSON, nullable=True)

    requested_by_user_id = Column(Integer, ForeignKey('User.user_id', ondelete='SET NULL'), nullable=True)
    requested_by_api_key_hash = Column(String(64), nullable=True)
    decided_by_user_id = Column(Integer, ForeignKey('User.user_id', ondelete='SET NULL'), nullable=True)
    decided_by_api_key_hash = Column(String(64), nullable=True)
    resolution_reason = Column(String(64), nullable=True)
    last_error = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=True)

    conversation = relationship('Conversation', foreign_keys=[conversation_id])

    __table_args__ = (
        Index(
            'ix_hitl_approval_pending_expires_at', 'expires_at',
            postgresql_where=text("status = 'pending'"),
        ),
        # A thread can only be paused once at a time. Rows being resolved (deciding/expiring)
        # are excluded: resuming one may pause the thread again and open the next approval.
        Index(
            'uq_hitl_approval_pending_conversation', 'conversation_id', unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )
