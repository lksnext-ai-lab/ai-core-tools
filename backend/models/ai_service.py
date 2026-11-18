import enum
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from models.base_service import BaseService
from models.service_lifecycle import ServiceLifecycleMixin
from models.service_health import ServiceHealthMixin, track_service_health

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

class AIService(ServiceLifecycleMixin, ServiceHealthMixin, BaseService):
    __tablename__ = 'AIService'
    
    provider = Column(String(45), nullable=False)
    supports_video = Column(Boolean, nullable=False, default=False, server_default='false')
    app_id = Column(Integer, ForeignKey('App.app_id'), nullable=True)  # NULL = system/platform service
    app = relationship('App', back_populates='ai_services') 

track_service_health(AIService)
