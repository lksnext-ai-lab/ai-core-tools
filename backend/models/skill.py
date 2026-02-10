from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime


class Skill(Base):
    """Skill model - Prompt-driven specializations for agents"""
    __tablename__ = 'Skill'

    skill_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String(1000))
    content = Column(Text, nullable=False)  # Markdown instructions for the skill

    # Timestamps
    create_date = Column(DateTime, default=datetime.now)
    update_date = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Foreign keys and relationships
    app_id = Column(Integer, ForeignKey('App.app_id'))
    app = relationship('App', back_populates='skills')
    agent_associations = relationship('AgentSkill', back_populates='skill')

    def get_associated_agents(self):
        """Retrieve all agents associated with this Skill."""
        return [association.agent for association in self.agent_associations]
