import enum
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Enum, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class MiddlewareType(enum.Enum):
    """LangChain middleware types an agent can attach (one of each per agent)."""
    SUMMARIZATION = "summarization"
    MODEL_CALL_LIMIT = "model_call_limit"
    TOOL_CALL_LIMIT = "tool_call_limit"
    PII = "pii"
    HUMAN_IN_THE_LOOP = "human_in_the_loop"
    GUARDRAILS = "guardrails"


class Middleware(Base):
    """App-scoped, reusable LangChain middleware configuration."""
    __tablename__ = 'Middleware'

    middleware_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String(1000))
    # Stored as the enum *name* in a plain VARCHAR (no native PG enum), matching the migrations.
    middleware_type = Column(Enum(MiddlewareType, native_enum=False, length=32), nullable=False)
    # Shape validated per type by schemas.middleware_schemas before it is stored.
    config = Column(JSON, nullable=True)

    create_date = Column(DateTime, default=datetime.now)
    update_date = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_frozen = Column(Boolean, default=False, nullable=False)

    app_id = Column(Integer, ForeignKey('App.app_id', ondelete='CASCADE'), nullable=False)
    app = relationship('App', back_populates='middlewares')
    agent_associations = relationship('AgentMiddleware', back_populates='middleware',
                                      cascade='all, delete-orphan', passive_deletes=True)

    __table_args__ = (
        UniqueConstraint('app_id', 'name', name='uq_middleware_app_name'),
    )


class AgentMiddleware(Base):
    __tablename__ = 'agent_middlewares'
    agent_id = Column(Integer, ForeignKey('Agent.agent_id', ondelete='CASCADE'), primary_key=True)
    middleware_id = Column(Integer, ForeignKey('Middleware.middleware_id', ondelete='CASCADE'),
                           primary_key=True, index=True)
    # Position in the agent's LangChain middleware chain (ascending).
    order = Column(Integer, nullable=False, default=0, server_default='0')
    agent = relationship('Agent', foreign_keys=[agent_id], back_populates='middleware_associations')
    middleware = relationship('Middleware', foreign_keys=[middleware_id], back_populates='agent_associations')
