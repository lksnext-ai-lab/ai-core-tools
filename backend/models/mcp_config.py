from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, Enum
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime
import enum
import json

class TransportType(enum.Enum):
    STDIO = "stdio"
    SSE = "sse"

class MCPConfig(Base):
    """MCP Client Configuration model"""
    __tablename__ = 'MCPConfig'

    config_id = Column(Integer, primary_key=True)
    name = Column(String(45), nullable=False)
    description = Column(String(1000))
    transport_type = Column(Enum(TransportType), nullable=False)
    
    # Common fields
    server_name = Column(String(45), nullable=False)
    create_date = Column(DateTime, default=datetime.now)
    update_date = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # STDIO specific fields
    command = Column(String(255))
    args = Column(JSON)  # List of strings
    env = Column(JSON)   # Dictionary of environment variables
    inputs = Column(JSON)  # List of input configurations
    encoding = Column(String(10), default="utf-8")
    encoding_error_handler = Column(String(10), default="strict")
    
    # SSE specific fields
    url = Column(String(255))
    headers = Column(JSON)  # Dictionary of HTTP headers
    timeout = Column(Integer, default=5)
    sse_read_timeout = Column(Integer, default=300)  # 5 minutes default
    
    # Foreign keys and relationships
    app_id = Column(Integer, ForeignKey('App.app_id'))
    app = relationship('App', back_populates='mcp_configs')
    agent_associations = relationship('AgentMCP', back_populates='mcp', cascade="all, delete-orphan")
    
    def get_associated_agents(self):
        """Retrieve all agents associated with this MCPConfig."""
        return [association.agent for association in self.agent_associations]

    def _parse_json_field(self, field, expected_type):
        """Helper to parse JSON fields safely"""
        if isinstance(field, expected_type):
            return field
        return json.loads(field) if field else None

    def _create_stdio_config(self) -> dict:
        """Create configuration for STDIO transport"""
        if not self.command or not self.args:
            raise ValueError("Command and args are required for STDIO transport")
        
        args = self._parse_json_field(self.args, list)
        return {
            self.server_name: {
                "command": self.command,
                "args": args,
                "transport": self.transport_type.value
            }
        }

    def _create_sse_config(self) -> dict:
        """Create configuration for SSE transport"""
        if not self.url:
            raise ValueError("URL is required for SSE transport")
            
        return {
            self.server_name: {
                "transport": self.transport_type.value,
                "url": self.url
            }
        }

    def to_connection_dict(self) -> dict:
        """Convert the model to a connection dictionary format expected by MultiServerMCPClient"""
        if self.transport_type == TransportType.STDIO:
            return self._create_stdio_config()
        return self._create_sse_config() 