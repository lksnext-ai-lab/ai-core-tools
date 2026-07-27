from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from db.database import Base

class ConversationStarter(Base):
    """
    Predefined prompts for marketplace agents to help users start a conversation.
    Linked 1:N to AgentMarketplaceProfile.
    """
    __tablename__ = 'ConversationStarter'

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(
        Integer, 
        ForeignKey('AgentMarketplaceProfile.id', ondelete='CASCADE'), 
        nullable=False
    )
    prompt = Column(String(500), nullable=False)
    order = Column(Integer, default=0, nullable=False)

    profile = relationship('AgentMarketplaceProfile', back_populates='conversation_starters')

    def __repr__(self):
        return f"<ConversationStarter(id={self.id}, prompt='{self.prompt[:20]}...')>"
