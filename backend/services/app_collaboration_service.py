from typing import List, Optional
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from models.app import App
from models.user import User
from db.session import SessionLocal
from utils.logger import get_logger
from sqlalchemy import and_
from sqlalchemy.orm import joinedload
from datetime import datetime

logger = get_logger(__name__)

class AppCollaborationService:
    
    @staticmethod
    def get_user_accessible_apps(user_id: int) -> List[App]:
        """Get all apps that a user can access (owned + collaborated)"""
        session = SessionLocal()
        try:
            # Get owned apps
            owned_apps = session.query(App).filter(App.owner_id == user_id).all()
            
            # Get collaborated apps (accepted collaborations only)
            collaborations = session.query(AppCollaborator).filter(
                AppCollaborator.user_id == user_id,
                AppCollaborator.status == CollaborationStatus.ACCEPTED
            ).all()
            
            collaborated_apps = [collab.app for collab in collaborations if collab.app]
            
            # Combine and remove duplicates
            all_apps = list({app.app_id: app for app in owned_apps + collaborated_apps}.values())
            
            # Sort by creation date, handling None values
            return sorted(all_apps, key=lambda x: x.create_date or datetime.min, reverse=True)
            
        finally:
            session.close()
    
    @staticmethod
    def can_user_manage_app(user_id: int, app_id: int) -> bool:
        """Check if user can manage an app (owner only)"""
        session = SessionLocal()
        try:
            # Check if user is owner
            app = session.query(App).filter(
                App.app_id == app_id,
                App.owner_id == user_id
            ).first()
            
            return app is not None
            
        finally:
            session.close()
    
    @staticmethod
    def can_user_access_app(user_id: int, app_id: int) -> bool:
        """Check if user can access an app (owner or accepted collaborator)"""
        session = SessionLocal()
        try:
            # Check if user is owner
            app = session.query(App).filter(
                App.app_id == app_id,
                App.owner_id == user_id
            ).first()
            
            if app:
                return True
            
            # Check if user is accepted collaborator
            collaboration = session.query(AppCollaborator).filter(
                AppCollaborator.app_id == app_id,
                AppCollaborator.user_id == user_id,
                AppCollaborator.status == CollaborationStatus.ACCEPTED
            ).first()
            
            return collaboration is not None
            
        finally:
            session.close()
    
    @staticmethod
    def get_user_app_role(user_id: int, app_id: int) -> Optional[str]:
        """Get the role of a user in an app"""
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
    
    # ============================================================================
    # COLLABORATION MANAGEMENT
    # ============================================================================
    
    @staticmethod
    def get_app_collaborators(app_id: int) -> List[AppCollaborator]:
        """Get all collaborators for an app"""
        session = SessionLocal()
        try:
            collaborators = session.query(AppCollaborator).options(
                joinedload(AppCollaborator.user),
                joinedload(AppCollaborator.inviter)
            ).filter(AppCollaborator.app_id == app_id).all()
            
            # Detach from session
            for collab in collaborators:
                session.expunge(collab)
                if collab.user:
                    session.expunge(collab.user)
                if collab.inviter:
                    session.expunge(collab.inviter)
            
            return collaborators
            
        finally:
            session.close()
    
    @staticmethod
    def invite_user_to_app(app_id: int, user_email: str, invited_by_user_id: int, role: str = "editor") -> Optional[AppCollaborator]:
        """Invite a user to collaborate on an app"""
        session = SessionLocal()
        try:
            # Validate app exists and inviter is owner
            app = session.query(App).filter(App.app_id == app_id).first()
            if not app:
                raise ValueError(f"App with ID {app_id} not found")
            
            if app.owner_id != invited_by_user_id:
                raise ValueError("Only app owners can invite collaborators")
            
            # Find user by email
            user = session.query(User).filter(User.email == user_email.lower().strip()).first()
            if not user:
                raise ValueError(f"User with email {user_email} not found")
            
            # Check if user is already the owner
            if user.user_id == app.owner_id:
                raise ValueError("Cannot invite the app owner as a collaborator")
            
            # Check if collaboration already exists
            existing_collab = session.query(AppCollaborator).filter(
                AppCollaborator.app_id == app_id,
                AppCollaborator.user_id == user.user_id
            ).first()
            
            if existing_collab:
                if existing_collab.status == CollaborationStatus.PENDING:
                    raise ValueError(f"User {user_email} already has a pending invitation")
                elif existing_collab.status == CollaborationStatus.ACCEPTED:
                    raise ValueError(f"User {user_email} is already a collaborator")
                else:  # DECLINED - allow re-invitation
                    existing_collab.status = CollaborationStatus.PENDING
                    existing_collab.role = CollaborationRole(role.lower())
                    existing_collab.invited_by = invited_by_user_id
                    existing_collab.invited_at = datetime.now()
                    existing_collab.accepted_at = None
                    session.commit()
                    session.refresh(existing_collab)
                    
                    # Load relationships and detach
                    session.expunge(existing_collab)
                    return existing_collab
            
            # Create new collaboration
            collaboration = AppCollaborator(
                app_id=app_id,
                user_id=user.user_id,
                role=CollaborationRole(role.lower()),
                invited_by=invited_by_user_id,
                status=CollaborationStatus.PENDING
            )
            
            session.add(collaboration)
            session.commit()
            session.refresh(collaboration)
            
            # Detach from session
            session.expunge(collaboration)
            
            logger.info(f"Invited user {user_email} to app {app_id} with role {role}")
            return collaboration
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error inviting user {user_email} to app {app_id}: {str(e)}")
            raise
        finally:
            session.close()
    
    @staticmethod
    def update_collaborator_role(app_id: int, user_id: int, new_role: str, updated_by_user_id: int) -> bool:
        """Update a collaborator's role"""
        session = SessionLocal()
        try:
            # Check if updater is owner
            app = session.query(App).filter(App.app_id == app_id).first()
            if not app or app.owner_id != updated_by_user_id:
                raise ValueError("Only app owners can update collaborator roles")
            
            # Find collaboration
            collaboration = session.query(AppCollaborator).filter(
                AppCollaborator.app_id == app_id,
                AppCollaborator.user_id == user_id
            ).first()
            
            if not collaboration:
                raise ValueError("Collaboration not found")
            
            if collaboration.status != CollaborationStatus.ACCEPTED:
                raise ValueError("Can only update roles for accepted collaborations")
            
            # Update role
            collaboration.role = CollaborationRole(new_role.lower())
            session.commit()
            
            logger.info(f"Updated role for user {user_id} in app {app_id} to {new_role}")
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating role for user {user_id} in app {app_id}: {str(e)}")
            raise
        finally:
            session.close()
    
    @staticmethod
    def remove_collaborator(app_id: int, user_id: int, removed_by_user_id: int) -> bool:
        """Remove a collaborator from an app"""
        session = SessionLocal()
        try:
            # Check if remover is owner
            app = session.query(App).filter(App.app_id == app_id).first()
            if not app or app.owner_id != removed_by_user_id:
                raise ValueError("Only app owners can remove collaborators")
            
            # Find collaboration
            collaboration = session.query(AppCollaborator).filter(
                AppCollaborator.app_id == app_id,
                AppCollaborator.user_id == user_id
            ).first()
            
            if not collaboration:
                raise ValueError("Collaboration not found")
            
            # Delete collaboration
            session.delete(collaboration)
            session.commit()
            
            logger.info(f"Removed user {user_id} from app {app_id}")
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error removing user {user_id} from app {app_id}: {str(e)}")
            raise
        finally:
            session.close()
    
    @staticmethod
    def respond_to_invitation(invitation_id: int, user_id: int, action: str) -> bool:
        """Respond to a collaboration invitation"""
        session = SessionLocal()
        try:
            collaboration = session.query(AppCollaborator).filter(
                AppCollaborator.id == invitation_id,
                AppCollaborator.user_id == user_id,
                AppCollaborator.status == CollaborationStatus.PENDING
            ).first()
            
            if not collaboration:
                return False
            
            if action == 'accept':
                collaboration.status = CollaborationStatus.ACCEPTED
                collaboration.accepted_at = datetime.now()
            elif action == 'decline':
                collaboration.status = CollaborationStatus.DECLINED
            else:
                return False
            
            session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error responding to invitation: {str(e)}")
            session.rollback()
            return False
        finally:
            session.close()

    @staticmethod
    def get_user_pending_invitations(user_id: int) -> List[AppCollaborator]:
        """Get all pending invitations for a user"""
        session = SessionLocal()
        try:
            invitations = session.query(AppCollaborator).options(
                joinedload(AppCollaborator.app),
                joinedload(AppCollaborator.inviter)
            ).filter(
                AppCollaborator.user_id == user_id,
                AppCollaborator.status == CollaborationStatus.PENDING
            ).all()
            
            return invitations
            
        except Exception as e:
            logger.error(f"Error getting pending invitations for user {user_id}: {str(e)}")
            return []
        finally:
            session.close() 