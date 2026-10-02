from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from db.database import Base
from enum import Enum
from datetime import datetime

class SiloType(Enum):
    CUSTOM = "CUSTOM"
    REPO = "REPO"
    DOMAIN = "DOMAIN"
    SHAREPOINT = "SHAREPOINT"
    
class Silo(Base):
    __tablename__ = 'Silo'
    silo_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    description = Column(Text)
    create_date = Column(DateTime, default=datetime.now)
    status = Column(String(45))
    silo_type = Column(String(45))  # Store as String in DB
    app_id = Column(Integer, ForeignKey('App.app_id'))
    app = relationship('App', back_populates='silos')
    fixed_metadata = Column(Boolean, default=False)
    metadata_definition_id = Column(Integer, ForeignKey('OutputParser.parser_id'), nullable=True)
    metadata_definition = relationship('OutputParser', uselist=False)
    embedding_service_id = Column(Integer, ForeignKey('embedding_service.service_id'), nullable=True)
    embedding_service = relationship('EmbeddingService', uselist=False)
    # Media (video/audio) indexing: transcription is required to index media into this silo,
    # the video service (supports_video) optionally adds visual analysis. Configured from the
    # silo itself or from the repository that owns it.
    transcription_service_id = Column(Integer, ForeignKey('AIService.service_id', ondelete='SET NULL'), nullable=True)
    video_ai_service_id = Column(Integer, ForeignKey('AIService.service_id', ondelete='SET NULL'), nullable=True)
    transcription_service = relationship('AIService', foreign_keys=[transcription_service_id])
    video_ai_service = relationship('AIService', foreign_keys=[video_ai_service_id])
    vector_db_type = Column(String(45), default='PGVECTOR')

    is_frozen = Column(Boolean, default=False, nullable=False)
    agents = relationship('Agent', lazy=True)
    repository = relationship('Repository', back_populates='silo')
    domain = relationship('Domain', back_populates='silo') 