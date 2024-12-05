from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey 
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class User(Base):
    '''User model class constructor'''
    __tablename__ = 'User'
    user_id = Column(Integer, primary_key=True)
    email = Column(String(255))
    name = Column(String(255))
    #domains = db.relationship('Domain', backref='user', lazy=True)
