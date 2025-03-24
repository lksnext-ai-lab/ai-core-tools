from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from db.base_class import Base
from datetime import datetime

class Url(Base):
    '''Url model class constructor'''
    __tablename__ = 'Url'
    url_id = Column(Integer, primary_key=True)
    url = Column(String(255))
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
    status = Column(String(45))
    
    domain_id = Column(Integer, ForeignKey('Domain.domain_id'), nullable=False)
    domain = relationship('Domain', back_populates='urls', foreign_keys=[domain_id])
    
