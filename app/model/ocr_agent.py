from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.model.agent import Agent


class OCRAgent(Agent):
    __tablename__ = 'OCRAgent'
    __table_args__ = {'extend_existing': True}
    
    agent_id = Column(Integer, ForeignKey('Agent.agent_id'), primary_key=True)
    
    # Only keep OCR-specific attributes
    vision_model_id = Column(Integer,
                        ForeignKey('Model.model_id'),
                        nullable=True)
    vision_system_prompt = Column(Text)
    text_system_prompt = Column(Text)
    
    vision_model_rel = relationship('Model',
                           foreign_keys=[vision_model_id])
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.type = 'ocr_agent'  # Ensure type is always set for OCR agents
    
    __mapper_args__ = {
        'polymorphic_identity': 'ocr_agent',
    }