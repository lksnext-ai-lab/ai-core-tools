from sqlalchemy import Column, Integer, ForeignKey, JSON, text
from sqlalchemy.orm import relationship
from .agent import Agent


class SystemOneAgent(Agent):
    """Agent that evaluates a text with a System One service and a fixed list of questions."""

    __tablename__ = 'SystemOneAgent'
    __table_args__ = {'extend_existing': True}

    agent_id = Column(Integer, ForeignKey('Agent.agent_id'), primary_key=True)
    # RESTRICT: a service in use cannot be deleted (the API answers 409 with the agents using it).
    system_one_service_id = Column(
        Integer, ForeignKey('SystemOneService.service_id', ondelete='RESTRICT'), nullable=False)
    # List of question dicts, validated by schemas.system_one_schemas.QuestionList.
    questions = Column(JSON, nullable=False)
    summarization_service_id = Column(
        Integer, ForeignKey('AIService.service_id', ondelete='SET NULL'), nullable=True)
    max_state_chars = Column(Integer, nullable=False, default=6000, server_default=text('6000'))

    system_one_service = relationship('SystemOneService', foreign_keys=[system_one_service_id])
    summarization_service = relationship('AIService', foreign_keys=[summarization_service_id])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.type = 'system_one_agent'

    __mapper_args__ = {'polymorphic_identity': 'system_one_agent'}
