from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime

class Media(Base):
    __tablename__ = 'Media'
    
    media_id = Column(Integer, primary_key=True)
    # Every media item is indexed into a silo; repository_id is set only for media managed
    # through a repository (media sent straight to a silo via the public API has none).
    silo_id = Column(Integer, ForeignKey('Silo.silo_id', ondelete='CASCADE'), nullable=False)
    repository_id = Column(Integer, ForeignKey('Repository.repository_id'), nullable=True)
    folder_id = Column(Integer, ForeignKey('Folder.folder_id'), nullable=True)
    transcription_service_id = Column(Integer, ForeignKey('AIService.service_id'), nullable=True)
    name = Column(String(255), nullable=False)
    source_type = Column(String(45), nullable=False)  # 'upload' | 'youtube'
    source_url = Column(String(500), nullable=True)
    file_path = Column(String(500), nullable=True)
    duration = Column(Float, nullable=True)
    language = Column(String(45), nullable=True)
    forced_language = Column(String(10), nullable=True)
    processing_mode = Column(String(20), default='basic')  # 'basic' | 'multimodal'
    chunk_min_duration = Column(Integer, nullable=True)  # in seconds
    chunk_max_duration = Column(Integer, nullable=True)  # in seconds
    chunk_overlap = Column(Integer, nullable=True)  # in seconds
    status = Column(String(45), default='pending')
    error_message = Column(Text, nullable=True)
    create_date = Column(DateTime, default=datetime.now)
    processed_at = Column(DateTime, nullable=True)
    # Caller metadata attached to every indexed chunk (public API); system keys win on conflict.
    custom_metadata = Column(JSON, nullable=True)
    
    # Relationships
    repository = relationship('Repository', back_populates='media', foreign_keys=[repository_id])
    folder = relationship('Folder', back_populates='media', foreign_keys=[folder_id])
    silo = relationship('Silo', foreign_keys=[silo_id])
    
    def __repr__(self):
        return f"<Media(media_id={self.media_id}, name='{self.name}', status='{self.status}')>"