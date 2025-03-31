from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, Table, DateTime
from sqlalchemy.orm import relationship
from db.base_class import Base
from datetime import datetime

class AgentTool(Base):
    __tablename__ = 'agent_tools'
    agent_id = Column(Integer, ForeignKey('Agent.agent_id'), primary_key=True)
    tool_id = Column(Integer, ForeignKey('Agent.agent_id'), primary_key=True)
    description = Column(Text, nullable=True)  # Description of what this tool is used for
    
    # Add relationships to both the agent and the tool
    agent = relationship('Agent', foreign_keys=[agent_id], back_populates='tool_associations')
    tool = relationship('Agent', foreign_keys=[tool_id])

class Agent(Base):
    __tablename__ = 'Agent'
    agent_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    description = Column(String(1000))
    create_date = Column(DateTime, default=datetime.now)
    system_prompt = Column(Text)
    prompt_template = Column(Text)
    type = Column(String(45), nullable=False, default='agent')
    status = Column(String(45))
    request_count = Column(Integer, default=0)
    is_tool = Column(Boolean, default=False)
    service_id = Column(Integer,
                        ForeignKey('AIService.service_id', ondelete='SET NULL'),
                        nullable=True)
    silo_id = Column(Integer,
                        ForeignKey('Silo.silo_id'),
                        nullable=True)
    app_id = Column(Integer,
                        ForeignKey('App.app_id'),
                        nullable=True)
    mcp_config_id = Column(Integer,
                        ForeignKey('MCPConfig.config_id'),
                        nullable=True)
    has_memory = Column(Boolean)
    output_parser_id = Column(Integer,
                        ForeignKey('OutputParser.parser_id'),
                        nullable=True)
    
    ai_service = relationship('AIService',
                           foreign_keys=[service_id])

    silo = relationship('Silo',
                           back_populates='agents',
                           foreign_keys=[silo_id])

    app = relationship('App',
                           back_populates='agents',
                           foreign_keys=[app_id])
    
    mcp_config = relationship('MCPConfig',
                           foreign_keys=[mcp_config_id])
    
    output_parser = relationship('OutputParser',
                           foreign_keys=[output_parser_id])
    
    # Modified relationship to use back_populates instead of backref
    tool_associations = relationship('AgentTool',
                                   primaryjoin=(agent_id == AgentTool.agent_id),
                                   back_populates='agent')
    
    __mapper_args__ = {
        'polymorphic_identity': 'agent',
        'polymorphic_on': type
    }
    
