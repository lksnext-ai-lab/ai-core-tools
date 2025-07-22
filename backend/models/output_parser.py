from sqlalchemy import Column, Integer, String, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from db.base import Base
from datetime import datetime

class OutputParser(Base):
    __tablename__ = 'OutputParser'
    parser_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    description = Column(String(1000))
    create_date = Column(DateTime, default=datetime.now)
    fields = Column(JSON)
    app_id = Column(Integer,
                    ForeignKey('App.app_id'),
                    nullable=True)
    
    app = relationship('App',
                      back_populates='output_parsers') 