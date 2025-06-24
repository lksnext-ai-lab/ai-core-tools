import enum
from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship
from model.base_service import BaseService

class EmbeddingProvider(enum.Enum):
    OpenAI = "OpenAI"
    MistralAI = "MistralAI"
    Ollama = "Ollama"
    Custom = "Custom"
    Azure = "Azure"

class EmbeddingService(BaseService):
    __tablename__ = 'embedding_service'
    
    provider = Column(String(45), nullable=False)
    app_id = Column(Integer, ForeignKey('App.app_id'), nullable=False)
    app = relationship('App', back_populates='embedding_services')