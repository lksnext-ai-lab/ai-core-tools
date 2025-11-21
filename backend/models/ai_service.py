import enum
from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship
from models.base_service import BaseService

class ProviderEnum(enum.Enum):
    OpenAI = "OpenAI"
    Anthropic = "Anthropic" 
    MistralAI = "MistralAI"
    Azure = "Azure"
    Custom = "Custom"
    Google = "Google"

class AIService(BaseService):
    __tablename__ = 'AIService'
    
    provider = Column(String(45), nullable=False)
    app_id = Column(Integer, ForeignKey('App.app_id'), nullable=False)
    app = relationship('App', back_populates='ai_services') 