import enum
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, Enum, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class MiddlewareType(enum.Enum):
    MONITORING = "monitoring"
    SUMMARIZATION = "summarization"
    MODEL_CALL_LIMIT = "model_call_limit"
    TOOL_CALL_LIMIT = "tool_call_limit"
    PII = "pii"
    HUMAN_IN_THE_LOOP = "human_in_the_loop"
    CUSTOM = "custom"
    GUARDRAILS = "guardrails"


class Middleware(Base):
    """Middleware model - LangChain middleware configurations for agents"""
    __tablename__ = 'Middleware'

    middleware_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String(1000))
    middleware_type = Column(Enum(MiddlewareType), nullable=False, default=MiddlewareType.MONITORING)
    config = Column(JSON, nullable=True)  # e.g. {"max_calls": 50}

    # Timestamps
    create_date = Column(DateTime, default=datetime.now)
    update_date = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_frozen = Column(Boolean, default=False, nullable=False)

    # Foreign keys and relationships
    app_id = Column(Integer, ForeignKey('App.app_id'))
    app = relationship('App', back_populates='middlewares')
    agent_associations = relationship('AgentMiddleware', back_populates='middleware')
    mcp_associations = relationship('MiddlewareMCP', back_populates='middleware', cascade='all, delete-orphan')

    # Name must be unique per app so agents can't accidentally attach two identically-named middlewares.
    __table_args__ = (
        UniqueConstraint('app_id', 'name', name='uq_middleware_app_name'),
    )

    def get_associated_agents(self):
        """Retrieve all agents associated with this Middleware."""
        return [association.agent for association in self.agent_associations]


class AgentMiddleware(Base):
    __tablename__ = 'agent_middlewares'
    agent_id = Column(Integer, ForeignKey('Agent.agent_id'), primary_key=True)
    middleware_id = Column(Integer, ForeignKey('Middleware.middleware_id'), primary_key=True)
    # Determines application order in the LangChain middleware chain (ascending).
    order = Column(Integer, nullable=False, default=0, server_default='0')
    agent = relationship('Agent', foreign_keys=[agent_id], back_populates='middleware_associations')
    middleware = relationship('Middleware', foreign_keys=[middleware_id], back_populates='agent_associations')


class MiddlewareMCP(Base):
    __tablename__ = 'middleware_mcps'
    middleware_id = Column(Integer, ForeignKey('Middleware.middleware_id', ondelete='CASCADE'), primary_key=True)
    config_id = Column(Integer, ForeignKey('MCPConfig.config_id', ondelete='CASCADE'), primary_key=True)
    middleware = relationship('Middleware', foreign_keys=[middleware_id], back_populates='mcp_associations')
    mcp = relationship('MCPConfig', foreign_keys=[config_id])
