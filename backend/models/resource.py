from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from db.base import Base
from datetime import datetime

class Resource(Base):
    __tablename__ = 'Resource'
    resource_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    create_date = Column(DateTime, default=datetime.now)
    uri = Column(String(1000))
    type = Column(String(45))
    status = Column(String(45))
    repository_id = Column(Integer,
                        ForeignKey('Repository.repository_id'),
                        nullable=True)

    repository = relationship('Repository',
                           back_populates='resources',
                           foreign_keys=[repository_id]) 