from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime

class App(Base):
    '''User model class constructor'''
    __tablename__ = 'App'
    app_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    slug = Column(String(100), unique=True, nullable=True)  # URL-safe identifier, system-wide unique
    agent_rate_limit = Column(Integer, default=0)
    max_file_size_mb = Column(Integer, default=0)
    agent_cors_origins = Column(String(1000))
    create_date = Column(DateTime, default=datetime.now)
    langsmith_api_key = Column(String(255))
    repositories = relationship('Repository', lazy=True)
    domains = relationship('Domain', back_populates='app', lazy=True)
    agents = relationship('Agent', lazy=True)
    ocr_agents = relationship('OCRAgent', lazy=True)
    output_parsers = relationship('OutputParser', 
                                back_populates='app',
                                lazy=True)
    owner_id = Column(Integer, ForeignKey('User.user_id'))
    owner = relationship('User', foreign_keys=[owner_id], back_populates='owned_apps')
    
    # Collaboration relationships
    collaborators = relationship('AppCollaborator', back_populates='app', lazy=True)
    
    api_keys = relationship('APIKey', back_populates='app', lazy=True)
    mcp_configs = relationship('MCPConfig', back_populates='app', lazy=True)
    skills = relationship('Skill', back_populates='app', lazy=True)

    silos = relationship('Silo', back_populates='app', lazy=True)
    ai_services = relationship('AIService', back_populates='app', lazy=True)
    embedding_services = relationship('EmbeddingService', back_populates='app', lazy=True)
    mcp_servers = relationship('MCPServer', back_populates='app', lazy=True)
    
    def get_user_role(self, user_id):
        """Get the role of a user in this app"""
        from services.app_collaboration_service import AppCollaborationService
        return AppCollaborationService.get_user_app_role(user_id, self.app_id) 