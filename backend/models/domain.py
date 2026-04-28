from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class Domain(Base):
    '''Domain model class constructor'''
    __tablename__ = 'Domain'
    domain_id = Column(Integer, primary_key=True)
    name = Column(String(45))
    create_date = Column(DateTime, default=datetime.now)
    description = Column(String(1000))
    base_url = Column(String(255))
    content_tag = Column(String(255))
    content_class = Column(String(255))
    content_id = Column(String(255))
    app_id = Column(Integer, ForeignKey('App.app_id'))
    app = relationship('App', back_populates='domains')

    # New relationships replacing the legacy Url relationship
    urls = relationship('DomainUrl', back_populates='domain', cascade='all, delete-orphan', lazy=True)
    crawl_policy = relationship('CrawlPolicy', uselist=False, back_populates='domain', cascade='all, delete-orphan')
    crawl_jobs = relationship('CrawlJob', back_populates='domain', cascade='all, delete-orphan', lazy=True)

    silo = relationship('Silo', lazy=False, uselist=False)
    silo_id = Column(Integer, ForeignKey('Silo.silo_id'), nullable=False)
