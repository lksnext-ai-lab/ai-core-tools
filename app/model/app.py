from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from db.base_class import Base
from model.output_parser import OutputParser
from datetime import datetime

class App(Base):
    '''User model class constructor'''
    __tablename__ = 'App'
    app_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    create_date = Column(DateTime, default=datetime.now)
    langsmith_api_key = Column(String(255))

    repositories = relationship('Repository', lazy=True)
    domains = relationship('Domain', back_populates='app', lazy=True)
    agents = relationship('Agent', lazy=True)
    ocr_agents = relationship('OCRAgent', lazy=True)
    output_parsers = relationship('OutputParser', 
                                back_populates='app',
                                lazy=True)
    user_id = Column(Integer, ForeignKey('User.user_id'))
    user = relationship('User', back_populates='apps')
    
    api_keys = relationship('APIKey', back_populates='app', lazy=True)
    mcp_configs = relationship('MCPConfig', back_populates='app', lazy=True)

    silos = relationship('Silo', back_populates='app', lazy=True)
    ai_services = relationship('AIService', back_populates='app', lazy=True)
    embedding_services = relationship('EmbeddingService', back_populates='app', lazy=True)
