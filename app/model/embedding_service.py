import enum
from sqlalchemy import Enum as SQLAEnum
from app.model.base_service import BaseService

class EmbeddingProvider(enum.Enum):
    OpenAI = "OpenAI"
    Custom = "Custom"

class EmbeddingService(BaseService):
    __tablename__ = 'embedding_service'
    
    provider = SQLAEnum(EmbeddingProvider, nullable=False)