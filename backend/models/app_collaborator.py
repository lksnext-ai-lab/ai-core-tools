from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from db.database import Base
from datetime import datetime
import enum

class CollaborationRole(enum.Enum):
    OWNER = "owner"
    ADMINISTRATOR = "administrator"
    EDITOR = "editor"

class CollaborationStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"

class AppCollaborator(Base):
    '''AppCollaborator model for managing app collaborations'''
    __tablename__ = 'AppCollaborator'
    
    id = Column(Integer, primary_key=True)
    app_id = Column(Integer, ForeignKey('App.app_id'), nullable=False)
    user_id = Column(Integer, ForeignKey('User.user_id'), nullable=False)
    role = Column(Enum(CollaborationRole), nullable=False, default=CollaborationRole.EDITOR)
    invited_by = Column(Integer, ForeignKey('User.user_id'), nullable=False)
    invited_at = Column(DateTime, default=datetime.now, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    status = Column(Enum(CollaborationStatus), nullable=False, default=CollaborationStatus.PENDING)
    
    # Relationships
    app = relationship('App', back_populates='collaborators')
    user = relationship('User', foreign_keys=[user_id], back_populates='app_collaborations')
    inviter = relationship('User', foreign_keys=[invited_by])
    
    def __repr__(self):
        return f"<AppCollaborator(app_id={self.app_id}, user_id={self.user_id}, role={self.role}, status={self.status})>" 