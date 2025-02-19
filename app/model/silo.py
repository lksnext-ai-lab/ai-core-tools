from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from enum import Enum

class SiloType(Enum):
    CUSTOM = "CUSTOM"
    REPO = "REPO"
    DOMAIN = "DOMAIN"
    
class Silo(Base):
    __tablename__ = 'Silo'
    silo_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    description = Column(Text)
    status = Column(String(45))
    silo_type = Column(String(45))  # Store as String in DB
    app_id = Column(Integer, ForeignKey('App.app_id'))
    app = relationship('App', back_populates='silos')
    fixed_metadata = Column(Boolean, default=False)
    metadata_definition_id = Column(Integer, ForeignKey('OutputParser.parser_id'), nullable=True)
    metadata_definition = relationship('OutputParser', uselist=False)

    agents = relationship('Agent', lazy=True)
    repository = relationship('Repository', back_populates='silo')
    
