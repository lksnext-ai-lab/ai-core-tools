from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from models.app_collaborator import AppCollaborator, CollaborationStatus, CollaborationRole
from models.app import App
from models.user import User
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

class AppCollaborationRepository:
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_accessible_apps(self, user_id: int) -> List[App]:
        """Get all apps that a user can access (owned + collaborated)"""
        # Get owned apps with owner relationship loaded
        owned_apps = self.db.query(App).options(joinedload(App.owner)).filter(App.owner_id == user_id).all()
        
        # Get collaborated apps (accepted collaborations only) with owner relationship loaded
        collaborations = self.db.query(AppCollaborator).options(
            joinedload(AppCollaborator.app).joinedload(App.owner)
        ).filter(
            AppCollaborator.user_id == user_id,
            AppCollaborator.status == CollaborationStatus.ACCEPTED
        ).all()
        
        collaborated_apps = [collab.app for collab in collaborations if collab.app]
        
        # Combine and remove duplicates
        all_apps = list({app.app_id: app for app in owned_apps + collaborated_apps}.values())
        
        # Sort by creation date, handling None values
        return sorted(all_apps, key=lambda x: x.create_date or datetime.min, reverse=True)
    
    def can_user_manage_app(self, user_id: int, app_id: int) -> bool:
        """Check if user can manage an app (owner only)"""
        app = self.db.query(App).filter(
            App.app_id == app_id,
            App.owner_id == user_id
        ).first()
        return app is not None
    
    def can_user_manage_collaborators(self, user_id: int, app_id: int) -> bool:
        """Check if user can manage collaborators (owner only)"""
        # Only the owner can manage collaborators
        app = self.db.query(App).filter(
            App.app_id == app_id,
            App.owner_id == user_id
        ).first()
        
        return app is not None
    
    def can_user_administer_app(self, user_id: int, app_id: int) -> bool:
        """Check if user can administer an app (owner or administrator)"""
        # Check if user is owner
        app = self.db.query(App).filter(
            App.app_id == app_id,
            App.owner_id == user_id
        ).first()
        
        if app:
            return True
        
        # Check if user is an administrator collaborator
        collaboration = self.db.query(AppCollaborator).filter(
            AppCollaborator.app_id == app_id,
            AppCollaborator.user_id == user_id,
            AppCollaborator.role == CollaborationRole.ADMINISTRATOR,
            AppCollaborator.status == CollaborationStatus.ACCEPTED
        ).first()
        
        return collaboration is not None
    
    def can_user_access_app(self, user_id: int, app_id: int) -> bool:
        """Check if user can access an app (owner or accepted collaborator)"""
        # Check if user is owner
        app = self.db.query(App).filter(
            App.app_id == app_id,
            App.owner_id == user_id
        ).first()
        
        if app:
            return True
        
        # Check if user is accepted collaborator
        collaboration = self.db.query(AppCollaborator).filter(
            AppCollaborator.app_id == app_id,
            AppCollaborator.user_id == user_id,
            AppCollaborator.status == CollaborationStatus.ACCEPTED
        ).first()
        
        return collaboration is not None
    
    def get_user_app_role(self, user_id: int, app_id: int) -> Optional[str]:
        """Get the role of a user in an app"""
        if not user_id or user_id <= 0 or not app_id or app_id <= 0:
            return None
        
        # Check if user is the owner
        app = self.db.query(App).filter(App.app_id == app_id).first()
        if app and app.owner_id == user_id:
            return "owner"
        
        # Check if user is a collaborator
        collaboration = self.db.query(AppCollaborator).filter(
            and_(
                AppCollaborator.app_id == app_id,
                AppCollaborator.user_id == user_id,
                AppCollaborator.status == CollaborationStatus.ACCEPTED
            )
        ).first()
        
        return collaboration.role.value if collaboration else None
    
    def get_app_collaborators(self, app_id: int) -> List[AppCollaborator]:
        """Get all collaborators for an app"""
        return self.db.query(AppCollaborator).options(
            joinedload(AppCollaborator.user),
            joinedload(AppCollaborator.inviter)
        ).filter(AppCollaborator.app_id == app_id).all()
    
    def get_collaboration_by_app_and_user(self, app_id: int, user_id: int) -> Optional[AppCollaborator]:
        """Get collaboration by app and user"""
        return self.db.query(AppCollaborator).filter(
            AppCollaborator.app_id == app_id,
            AppCollaborator.user_id == user_id
        ).first()
    
    def get_collaboration_by_id(self, collaboration_id: int) -> Optional[AppCollaborator]:
        """Get collaboration by ID"""
        return self.db.query(AppCollaborator).filter(AppCollaborator.id == collaboration_id).first()
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        return self.db.query(User).filter(User.email == email.lower().strip()).first()
    
    def create_collaboration(self, collaboration_data: dict) -> AppCollaborator:
        """Create a new collaboration"""
        collaboration = AppCollaborator(**collaboration_data)
        self.db.add(collaboration)
        self.db.commit()
        self.db.refresh(collaboration)
        return collaboration
    
    def update_collaboration(self, collaboration: AppCollaborator, update_data: dict) -> AppCollaborator:
        """Update an existing collaboration"""
        for key, value in update_data.items():
            if hasattr(collaboration, key):
                setattr(collaboration, key, value)
        
        self.db.add(collaboration)
        self.db.commit()
        self.db.refresh(collaboration)
        return collaboration
    
    def delete_collaboration(self, collaboration: AppCollaborator) -> bool:
        """Delete a collaboration"""
        try:
            self.db.delete(collaboration)
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting collaboration {collaboration.id}: {e}")
            self.db.rollback()
            return False
    
    def get_user_pending_invitations(self, user_id: int) -> List[AppCollaborator]:
        """Get all pending invitations for a user"""
        return self.db.query(AppCollaborator).options(
            joinedload(AppCollaborator.app),
            joinedload(AppCollaborator.inviter)
        ).filter(
            AppCollaborator.user_id == user_id,
            AppCollaborator.status == CollaborationStatus.PENDING
        ).all()
    
    def get_collaborations_by_app(self, app_id: int) -> List[AppCollaborator]:
        """Get all collaborations for an app (for deletion)"""
        return self.db.query(AppCollaborator).filter(AppCollaborator.app_id == app_id).all()
