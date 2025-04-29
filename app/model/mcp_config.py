from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, Enum
from sqlalchemy.orm import relationship
from db.base_class import Base
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

    def to_connection_dict(self) -> dict:
        """Convert the model to a connection dictionary format expected by MultiServerMCPClient"""
        if self.transport_type == TransportType.STDIO:
            if not self.command or not self.args:
                raise ValueError("Command and args are required for STDIO transport")
            
            # Ensure args and env are proper Python objects, not strings
            args = self.args if isinstance(self.args, list) else json.loads(self.args)
            env = self.env if isinstance(self.env, dict) else json.loads(self.env) if self.env else None
            inputs = self.inputs if isinstance(self.inputs, list) else json.loads(self.inputs) if self.inputs else None
            
            config = {
                        self.server_name: {
                            "command": self.command,
                            "args": args,
                            "transport": self.transport_type.value
                        }
                    }
            """
            # Add env if exists
            if env:
                config[self.server_name]["env"] = env
            
            # Add inputs if exists
            if inputs:
                config["inputs"] = inputs            
            """

                
            return config
            
        elif self.transport_type == TransportType.SSE:
            if not self.url:
                raise ValueError("URL is required for SSE transport")
            base_config = {
                self.server_name: {
                    "transport": self.transport_type.value,
                    "url": self.url
                }
            }
            
            """
            # Añadir headers si existen
            if self.headers:
                base_config["headers"] = self.headers
            if self.timeout:
                base_config["timeout"] = self.timeout
            if self.sse_read_timeout:
                base_config["sse_read_timeout"] = self.sse_read_timeout            
            """

            return base_config