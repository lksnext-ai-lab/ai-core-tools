from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime

class Media(Base):
    __tablename__ = 'Media'
    
    media_id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey('Repository.repository_id'), nullable=False)
    folder_id = Column(Integer, ForeignKey('Folder.folder_id'), nullable=True)
    transcription_service_id = Column(Integer, ForeignKey('AIService.service_id'), nullable=True)  # ADD THIS
    name = Column(String(255), nullable=False)
    source_type = Column(String(45), nullable=False)  # 'upload' | 'youtube'
    source_url = Column(String(500), nullable=True)
    file_path = Column(String(500), nullable=True)
    duration = Column(Float, nullable=True)
    language = Column(String(45), nullable=True)
    forced_language = Column(String(10), nullable=True)
    chunk_min_duration = Column(Integer, nullable=True)  # in seconds
    chunk_max_duration = Column(Integer, nullable=True)  # in seconds
    chunk_overlap = Column(Integer, nullable=True)  # in seconds
    status = Column(String(45), default='pending')
    error_message = Column(Text, nullable=True)
    create_date = Column(DateTime, default=datetime.now)
    processed_at = Column(DateTime, nullable=True)
    
    # Relationships
    repository = relationship('Repository', back_populates='media', foreign_keys=[repository_id])
    folder = relationship('Folder', back_populates='media', foreign_keys=[folder_id])
    
    def __repr__(self):
        return f"<Media(media_id={self.media_id}, name='{self.name}', status='{self.status}')>"