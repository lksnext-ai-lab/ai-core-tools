from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, Boolean
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime
import json

class MCPConfig(Base):
    """MCP Client Configuration model - Simplified"""
    __tablename__ = 'MCPConfig'

    config_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String(1000))
    config = Column(JSON, nullable=False)  # Full MCP server config as JSON
    
    # Timestamps
    create_date = Column(DateTime, default=datetime.now)
    update_date = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Foreign keys and relationships
    app_id = Column(Integer, ForeignKey('App.app_id'))
    app = relationship('App', back_populates='mcp_configs')
    agent_associations = relationship('AgentMCP', back_populates='mcp')
    
    def get_associated_agents(self):
        """Retrieve all agents associated with this MCPConfig."""
        return [association.agent for association in self.agent_associations]

    def to_connection_dict(self) -> dict:
        """Convert the model to a connection dictionary format expected by MultiServerMCPClient
        
        The config field should contain the full MCP server configuration, e.g.:
        {
            "playwright": {
                "command": "npx",
                "args": ["@playwright/mcp@latest", "--isolated"]
            }
        }
        """
        if isinstance(self.config, dict):
            return self.config
        elif isinstance(self.config, str):
            return json.loads(self.config)
        return {} 