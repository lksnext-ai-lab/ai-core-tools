from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey 
from sqlalchemy.orm import relationship
from db.base_class import Base


class Model(Base):
    '''User model class constructor'''
    __tablename__ = 'Model'
    model_id = Column(Integer, primary_key=True)
    provider = Column(String(45))
    name = Column(String(45))
    description = Column(String(1000))

