from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey 
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class Silo(Base):
    __tablename__ = 'Silo'
    silo_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    description = Column(Text)
    status = Column(String(45))
    app_id = Column(Integer, ForeignKey('App.app_id'))
    app = relationship('App', back_populates='silos')
    fixed_metadata = Column(Boolean, default=False)
    metadata_definition_id = Column(Integer, ForeignKey('OutputParser.parser_id'), nullable=True)
    metadata_definition = relationship('OutputParser', uselist=False)
    
