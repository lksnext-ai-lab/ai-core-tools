from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey 
from sqlalchemy.orm import relationship
from db.base_class import Base


class Repository(Base):
    __tablename__ = 'Repository'
    repository_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    type = Column(String(45))
    status = Column(String(45))
    app_id = Column(Integer,
                        ForeignKey('App.app_id'),
                        nullable=True)

    app = relationship('App',
                           back_populates='repositories',
                           foreign_keys=[app_id])
    
    resources = relationship('Resource', lazy=True)
    
    agents = relationship('Agent', lazy=True)

