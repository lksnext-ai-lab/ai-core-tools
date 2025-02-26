import enum
from sqlalchemy import Column, Integer, String, Enum as SQLAEnum
from app.db.base_class import Base

class ProviderEnum(enum.Enum):
    OpenAI = "OpenAI"
    Anthropic = "Anthropic"
    MistralAI = "MistralAI"
    Custom = "Custom"

class AIService(Base):
    __tablename__ = 'AIService'
    
    service_id = Column(Integer, primary_key=True, index=True)
    provider = Column(SQLAEnum(ProviderEnum), nullable=False)
    name = Column(String(100), nullable=False)
    endpoint = Column(String(255), nullable=True)
    api_key = Column(String(255), nullable=True)
    description = Column(String(1000), nullable=True)
