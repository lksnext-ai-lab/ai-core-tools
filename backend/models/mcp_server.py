from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class MCPServerAgent(Base):
    """Association table for MCP servers and agents exposed as tools"""
    __tablename__ = 'mcp_server_agents'

    server_id = Column(Integer, ForeignKey('MCPServer.server_id', ondelete='CASCADE'), primary_key=True)
    agent_id = Column(Integer, ForeignKey('Agent.agent_id', ondelete='CASCADE'), primary_key=True)
    tool_name_override = Column(String(100), nullable=True)  # Optional custom tool name
    tool_description_override = Column(String(1000), nullable=True)  # Optional custom description

    mcp_server = relationship('MCPServer', back_populates='agent_associations')
    agent = relationship('Agent')


class MCPServer(Base):
    """MCP Server that exposes agents as MCP tools for external clients"""
    __tablename__ = 'MCPServer'

    server_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False)  # URL-safe identifier, unique within app
    description = Column(String(1000), nullable=True)
    is_active = Column(Boolean, default=True)
    rate_limit = Column(Integer, default=0)  # Requests per minute, 0 = unlimited

    create_date = Column(DateTime, default=datetime.now)
    update_date = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    app_id = Column(Integer, ForeignKey('App.app_id', ondelete='CASCADE'), nullable=False)

    # Relationships
    app = relationship('App', back_populates='mcp_servers')
    agent_associations = relationship('MCPServerAgent',
                                      back_populates='mcp_server',
                                      cascade='all, delete-orphan',
                                      lazy='joined')

    # Unique constraint: slug must be unique per app
    __table_args__ = (
        UniqueConstraint('app_id', 'slug', name='uq_mcp_server_app_slug'),
    )
