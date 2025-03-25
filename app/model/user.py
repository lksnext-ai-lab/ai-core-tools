from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from db.base_class import Base
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, Base):
    '''User model class constructor'''
    __tablename__ = 'User'
    user_id = Column(Integer, primary_key=True)
    email = Column(String(255))
    name = Column(String(255))
    create_date = Column(DateTime, default=datetime.now)
    apps = relationship('App', back_populates='user', lazy=True)
    
    api_keys = relationship('APIKey', back_populates='user', lazy=True)

    def get_id(self):
        return self.user_id