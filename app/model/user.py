from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey 
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from flask_login import UserMixin
class User(UserMixin, Base):
    '''User model class constructor'''
    __tablename__ = 'User'
    user_id = Column(Integer, primary_key=True)
    email = Column(String(255))
    name = Column(String(255))
    #domains = db.relationship('Domain', backref='user', lazy=True)

    apps = relationship('App', back_populates='user', lazy=True)
    
    def api_keys(self):
        from app.model.api_key import APIKey
        return relationship('APIKey', back_populates='user', lazy=True)

    # Add this method required by Flask-Login
    def get_id(self):
        return str(self.user_id)