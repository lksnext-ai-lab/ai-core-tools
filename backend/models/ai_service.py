import enum
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, SmallInteger
from sqlalchemy.orm import relationship
from models.base_service import BaseService

class ProviderEnum(enum.Enum):
    OpenAI = "OpenAI"
    Anthropic = "Anthropic" 
    MistralAI = "MistralAI"
    Azure = "Azure"
    Custom = "Custom"
    Google = "Google"
    GoogleCloud = "GoogleCloud"
    OpenRouter = "OpenRouter"
    Bedrock = "Bedrock"


class AIService(BaseService):
    __tablename__ = 'AIService'
    
    provider = Column(String(45), nullable=False)
    supports_video = Column(Boolean, nullable=False, default=False, server_default='false')
    app_id = Column(Integer, ForeignKey('App.app_id'), nullable=True)  # NULL = system/platform service
    execution_profile = Column(SmallInteger, nullable=False, default=1, server_default='1')
    app = relationship('App', back_populates='ai_services') 