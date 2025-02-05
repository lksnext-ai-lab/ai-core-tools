from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class OCRAgent(Base):
    __tablename__ = 'OCRAgent'
    __table_args__ = {'extend_existing': True}
    agent_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    description = Column(String(1000))
    request_count = Column(Integer, default=0)
    vision_model_id = Column(Integer,
                        ForeignKey('Model.model_id'),
                        nullable=True)
    model_id = Column(Integer,
                        ForeignKey('Model.model_id'),
                        nullable=True)
    vision_system_prompt = Column(Text)
    text_system_prompt = Column(Text)
    app_id = Column(Integer,
                        ForeignKey('App.app_id'),
                        nullable=True)
    output_parser_id = Column(Integer,
                        ForeignKey('OutputParser.parser_id'),
                        nullable=True)
    
    vision_model_rel = relationship('Model',
                           foreign_keys=[vision_model_id])
    
    model_rel = relationship('Model',
                           foreign_keys=[model_id])
    
    app = relationship('App',
                           back_populates='ocr_agents',
                           foreign_keys=[app_id])
    
    output_parser = relationship('OutputParser',
                           foreign_keys=[output_parser_id])