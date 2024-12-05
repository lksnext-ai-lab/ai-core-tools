from sqlalchemy import Column, Integer, String, JSON, ForeignKey 
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class OutputParser(Base):
    __tablename__ = 'OutputParser'
    parser_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    description = Column(String(1000))
    fields = Column(JSON)
    app_id = Column(Integer,
                    ForeignKey('App.app_id'),
                    nullable=True)
    
    app = relationship('App',
                      back_populates='output_parsers') 