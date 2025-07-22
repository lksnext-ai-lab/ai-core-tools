from typing import List, Optional
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from models.app import App
from db.session import SessionLocal
from utils.logger import get_logger
from sqlalchemy import and_

logger = get_logger(__name__)

class AppCollaborationService:
    
    @staticmethod
    def get_user_accessible_apps(user_id: int) -> List[App]:
        """Get all apps that a user can access (owned + collaborated)"""
        session = SessionLocal()
        try:
            # Get owned apps
            owned_apps = session.query(App).filter(App.owner_id == user_id).all()
            
            # Get collaborated apps
            collaborations = session.query(AppCollaborator).filter(
                AppCollaborator.user_id == user_id
            ).all()
            
            collaborated_apps = [collab.app for collab in collaborations if collab.app]
            
            # Combine and remove duplicates
            all_apps = list({app.app_id: app for app in owned_apps + collaborated_apps}.values())
            
            # Sort by creation date
            return sorted(all_apps, key=lambda x: x.create_date, reverse=True)
            
        finally:
            session.close()
    
    @staticmethod
    def can_user_manage_app(user_id: int, app_id: int) -> bool:
        """Check if user can manage an app (owner or admin)"""
        session = SessionLocal()
        try:
            # Check if user is owner
            app = session.query(App).filter(
                App.app_id == app_id,
                App.owner_id == user_id
            ).first()
            
            if app:
                return True
            
            # Check if user is admin collaborator
            collaboration = session.query(AppCollaborator).filter(
                AppCollaborator.app_id == app_id,
                AppCollaborator.user_id == user_id,
                AppCollaborator.role == CollaborationRole.ADMIN
            ).first()
            
            return collaboration is not None
            
        finally:
            session.close()
    
    @staticmethod
    def get_user_app_role(user_id: int, app_id: int) -> Optional[str]:
        """
        Get the role of a user in an app
        
        Args:
            user_id: ID of the user
            app_id: ID of the app
            
        Returns:
            Role string or None if user has no access
        """
        if not user_id or user_id <= 0 or not app_id or app_id <= 0:
            return None
        
        session = SessionLocal()
        try:
            # Check if user is the owner
            app = session.query(App).filter(App.app_id == app_id).first()
            if app and app.owner_id == user_id:
                return "owner"
            
            # Check if user is a collaborator
            collaboration = session.query(AppCollaborator).filter(
                and_(
                    AppCollaborator.app_id == app_id,
                    AppCollaborator.user_id == user_id,
                    AppCollaborator.status == CollaborationStatus.ACCEPTED
                )
            ).first()
            
            return collaboration.role.value if collaboration else None
            
        except Exception as e:
            logger.warning(f"Error getting role for user {user_id} in app {app_id}: {str(e)}")
            return None
        finally:
            session.close() 