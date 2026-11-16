from sqlalchemy import Column, Integer, String, JSON, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime

class OutputParser(Base):
    __tablename__ = 'OutputParser'
    parser_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    description = Column(String(1000))
    create_date = Column(DateTime, default=datetime.now)
    fields = Column(JSON)
    is_enum = Column(Boolean, nullable=False, default=False, server_default='false')
    app_id = Column(Integer,
                    ForeignKey('App.app_id'),
                    nullable=True)
    
    app = relationship('App',
                      back_populates='output_parsers') 