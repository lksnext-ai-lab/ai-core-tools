from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from db.base_class import Base
from model.url import Url

class Domain(Base):
    '''Domain model class constructor'''
    __tablename__ = 'Domain'
    domain_id = Column(Integer, primary_key=True)
    name = Column(String(45))
    description = Column(String(1000))
    base_url = Column(String(255))
    content_tag = Column(String(255))
    content_class = Column(String(255))
    content_id = Column(String(255))
    app_id = Column(Integer, ForeignKey('App.app_id'))
    app = relationship('App', back_populates='domains')
    urls = relationship(Url, lazy=True)

    silo = relationship('Silo', lazy=False, uselist=False)
    silo_id = Column(Integer, ForeignKey('Silo.silo_id'), nullable=False)

    
    
