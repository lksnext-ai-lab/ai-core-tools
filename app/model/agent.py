from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey 
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class Agent(Base):
    __tablename__ = 'Agent'
    agent_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    description = Column(String(1000))
    system_prompt = Column(Text)
    prompt_template = Column(Text)
    type = Column(String(45), nullable=False, default='agent')
    status = Column(String(45))
    request_count = Column(Integer, default=0)
    model_id = Column(Integer,
                        ForeignKey('Model.model_id'),
                        nullable=True)
    silo_id = Column(Integer,
                        ForeignKey('Silo.silo_id'),
                        nullable=True)
    app_id = Column(Integer,
                        ForeignKey('App.app_id'),
                        nullable=True)
    has_memory = Column(Boolean)
    output_parser_id = Column(Integer,
                        ForeignKey('OutputParser.parser_id'),
                        nullable=True)
    
    model = relationship('Model',
                           foreign_keys=[model_id])

    silo = relationship('Silo',
                           back_populates='agents',
                           foreign_keys=[silo_id])

    app = relationship('App',
                           back_populates='agents',
                           foreign_keys=[app_id])
    
    output_parser = relationship('OutputParser',
                           foreign_keys=[output_parser_id])
    
    __mapper_args__ = {
        'polymorphic_identity': 'agent',
        'polymorphic_on': type
    }
    
