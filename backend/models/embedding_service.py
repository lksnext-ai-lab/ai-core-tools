import enum
from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship
from models.base_service import BaseService
from models.service_health import ServiceHealthMixin, track_service_health

class EmbeddingProvider(enum.Enum):
    OpenAI = "OpenAI"
    MistralAI = "MistralAI"
    Ollama = "Ollama"
    Custom = "Custom"
    Azure = "Azure"
    Google = "Google"
    GoogleCloud = "GoogleCloud"
    Bedrock = "Bedrock"

class EmbeddingService(ServiceHealthMixin, BaseService):
    __tablename__ = 'embedding_service'

    provider = Column(String(45), nullable=False)
    app_id = Column(Integer, ForeignKey('App.app_id'), nullable=True)  # NULL = system/platform service
    app = relationship('App', back_populates='embedding_services')


track_service_health(EmbeddingService)
