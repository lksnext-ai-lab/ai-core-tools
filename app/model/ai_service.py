import enum
from sqlalchemy import Column, String
from app.model.base_service import BaseService

class ProviderEnum(enum.Enum):
    OpenAI = "OpenAI"
    Anthropic = "Anthropic"
    MistralAI = "MistralAI"
    Custom = "Custom"

class AIService(BaseService):
    __tablename__ = 'AIService'
    
    provider = Column(String(45), nullable=False)