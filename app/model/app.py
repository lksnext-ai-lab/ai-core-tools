from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey 
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from app.model.output_parser import OutputParser

class App(Base):
    '''User model class constructor'''
    __tablename__ = 'App'
    app_id = Column(Integer, primary_key=True)
    name = Column(String(255))

    repositories = relationship('Repository', lazy=True)
    agents = relationship('Agent', lazy=True)
    ocr_agents = relationship('OCRAgent', lazy=True)
    output_parsers = relationship('OutputParser', 
                                back_populates='app',
                                lazy=True)
    user_id = Column(Integer, ForeignKey('User.user_id'))
    user = relationship('User', back_populates='apps')

    def api_keys(self):
        from app.model.api_key import APIKey
        return relationship('APIKey', back_populates='app', lazy=True)
