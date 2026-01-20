from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime

class MediaChunk(Base):
    __tablename__ = 'MediaChunk'
    
    chunk_id = Column(Integer, primary_key=True)
    media_id = Column(Integer, ForeignKey('Media.media_id'), nullable=False)
    text = Column(Text, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    create_date = Column(DateTime, default=datetime.now)
    
    # Relationships
    media = relationship('Media', back_populates='chunks', foreign_keys=[media_id])
    
    def __repr__(self):
        return f"<MediaChunk(chunk_id={self.chunk_id}, media_id={self.media_id}, index={self.chunk_index})>"