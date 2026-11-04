from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime

RESOURCE_STATUS_INDEXED = 'indexed'
RESOURCE_STATUS_ERROR = 'error'

class Resource(Base):
    __tablename__ = 'Resource'
    resource_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    create_date = Column(DateTime, default=datetime.now)
    uri = Column(String(1000))
    type = Column(String(45))
    status = Column(String(45))  # indexed | error (NULL for documents indexed before it was tracked)
    error_message = Column(Text, nullable=True)  # why the last indexing failed
    repository_id = Column(Integer,
                        ForeignKey('Repository.repository_id'),
                        nullable=True)
    folder_id = Column(Integer,
                       ForeignKey('Folder.folder_id'),
                       nullable=True)

    repository = relationship('Repository',
                           back_populates='resources',
                           foreign_keys=[repository_id])
    folder = relationship('Folder',
                         back_populates='resources',
                         foreign_keys=[folder_id]) 