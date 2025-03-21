import enum
from sqlalchemy import Column, String
from app.model.base_service import BaseService

class EmbeddingProvider(enum.Enum):
    OpenAI = "OpenAI"
    Custom = "Custom"

class EmbeddingService(BaseService):
    __tablename__ = 'embedding_service'
    
    provider = Column(String(45), nullable=False)