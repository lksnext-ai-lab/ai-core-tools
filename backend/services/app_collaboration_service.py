from typing import List, Optional
from sqlalchemy.orm import Session
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from models.app import App
from repositories.app_collaboration_repository import AppCollaborationRepository
from utils.logger import get_logger
from datetime import datetime

logger = get_logger(__name__)

class AppCollaborationService:
    
    def __init__(self, db: Session):
        self.db = db
        self.repo = AppCollaborationRepository(db)
    
    def get_user_accessible_apps(self, user_id: int) -> List[App]:
        """Get all apps that a user can access (owned + collaborated)"""
        return self.repo.get_user_accessible_apps(user_id)
    
    def can_user_manage_app(self, user_id: int, app_id: int) -> bool:
        """Check if user can manage an app (owner only)"""
        return self.repo.can_user_manage_app(user_id, app_id)
    
    def can_user_manage_collaborators(self, user_id: int, app_id: int) -> bool:
        """Check if user can manage collaborators (owner only)"""
        return self.repo.can_user_manage_collaborators(user_id, app_id)
    
    def can_user_administer_app(self, user_id: int, app_id: int) -> bool:
        """Check if user can administer an app (owner or administrator)"""
        return self.repo.can_user_administer_app(user_id, app_id)
    
    def can_user_access_app(self, user_id: int, app_id: int) -> bool:
        """Check if user can access an app (owner or accepted collaborator)"""
        return self.repo.can_user_access_app(user_id, app_id)
    
    def get_user_app_role(self, user_id: int, app_id: int) -> Optional[str]:
        """Get the role of a user in an app"""
        if not user_id or user_id <= 0 or not app_id or app_id <= 0:
            return None
        
        try:
            return self.repo.get_user_app_role(user_id, app_id)
        except Exception as e:
            logger.warning(f"Error getting role for user {user_id} in app {app_id}: {str(e)}")
            return None
    
    # ============================================================================
    # COLLABORATION MANAGEMENT
    # ============================================================================
    
    def get_app_collaborators(self, app_id: int) -> List[AppCollaborator]:
        """Get all collaborators for an app"""
        return self.repo.get_app_collaborators(app_id)
    
    def invite_user_to_app(self, app_id: int, user_email: str, invited_by_user_id: int, role: str = "editor") -> Optional[AppCollaborator]:
        """Invite a user to collaborate on an app"""
        try:
            # Validate app exists and inviter is owner (only owners can manage collaborators)
            if not self.repo.can_user_manage_app(invited_by_user_id, app_id):
                raise ValueError("Only app owners can invite collaborators")
            
            # Find user by email
            user = self.repo.get_user_by_email(user_email)
            if not user:
                raise ValueError(f"User with email {user_email} not found")
            
            # Check if user is already the owner
            if self.repo.can_user_manage_app(user.user_id, app_id):
                raise ValueError("Cannot invite the app owner as a collaborator")
            
            # Check if collaboration already exists
            existing_collab = self.repo.get_collaboration_by_app_and_user(app_id, user.user_id)
            
            if existing_collab:
                if existing_collab.status == CollaborationStatus.PENDING:
                    raise ValueError(f"User {user_email} already has a pending invitation")
                elif existing_collab.status == CollaborationStatus.ACCEPTED:
                    raise ValueError(f"User {user_email} is already a collaborator")
                else:  # DECLINED - allow re-invitation
                    update_data = {
                        'status': CollaborationStatus.PENDING,
                        'role': CollaborationRole(role.lower()),
                        'invited_by': invited_by_user_id,
                        'invited_at': datetime.now(),
                        'accepted_at': None
                    }
                    return self.repo.update_collaboration(existing_collab, update_data)
            
            # Create new collaboration
            collaboration_data = {
                'app_id': app_id,
                'user_id': user.user_id,
                'role': CollaborationRole(role.lower()),
                'invited_by': invited_by_user_id,
                'status': CollaborationStatus.PENDING
            }
            
            collaboration = self.repo.create_collaboration(collaboration_data)
            
            logger.info(f"Invited user {user_email} to app {app_id} with role {role}")
            return collaboration
            
        except Exception as e:
            logger.error(f"Error inviting user {user_email} to app {app_id}: {str(e)}")
            raise
    
    def update_collaborator_role(self, app_id: int, user_id: int, new_role: str, updated_by_user_id: int) -> bool:
        """Update a collaborator's role"""
        try:
            # Check if updater is owner
            if not self.repo.can_user_manage_app(updated_by_user_id, app_id):
                raise ValueError("Only app owners can update collaborator roles")
            
            # Find collaboration
            collaboration = self.repo.get_collaboration_by_app_and_user(app_id, user_id)
            if not collaboration:
                raise ValueError("Collaboration not found")
            
            if collaboration.status != CollaborationStatus.ACCEPTED:
                raise ValueError("Can only update roles for accepted collaborations")
            
            # Update role
            update_data = {'role': CollaborationRole(new_role.lower())}
            self.repo.update_collaboration(collaboration, update_data)
            
            logger.info(f"Updated role for user {user_id} in app {app_id} to {new_role}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating role for user {user_id} in app {app_id}: {str(e)}")
            raise
    
    def remove_collaborator(self, app_id: int, user_id: int, removed_by_user_id: int) -> bool:
        """Remove a collaborator from an app"""
        try:
            # Check if remover is owner
            if not self.repo.can_user_manage_app(removed_by_user_id, app_id):
                raise ValueError("Only app owners can remove collaborators")
            
            # Find collaboration
            collaboration = self.repo.get_collaboration_by_app_and_user(app_id, user_id)
            if not collaboration:
                raise ValueError("Collaboration not found")
            
            # Delete collaboration
            success = self.repo.delete_collaboration(collaboration)
            
            if success:
                logger.info(f"Removed user {user_id} from app {app_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error removing user {user_id} from app {app_id}: {str(e)}")
            raise
    
    def leave_app_collaboration(self, app_id: int, user_id: int) -> bool:
        """Allow a collaborator to leave an app collaboration themselves"""
        try:
            # Find collaboration
            collaboration = self.repo.get_collaboration_by_app_and_user(app_id, user_id)
            if not collaboration:
                raise ValueError("Collaboration not found")
            
            # Check if user is the owner (owners cannot leave their own apps)
            if self.repo.can_user_manage_app(user_id, app_id):
                raise ValueError("App owners cannot leave their own apps")
            
            # Check if collaboration is accepted
            if collaboration.status != CollaborationStatus.ACCEPTED:
                raise ValueError("Can only leave accepted collaborations")
            
            # Delete collaboration
            success = self.repo.delete_collaboration(collaboration)
            
            if success:
                logger.info(f"User {user_id} left app {app_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error leaving app {app_id} for user {user_id}: {str(e)}")
            raise
    
    def respond_to_invitation(self, invitation_id: int, user_id: int, action: str) -> bool:
        """Respond to a collaboration invitation"""
        try:
            collaboration = self.repo.get_collaboration_by_id(invitation_id)
            
            if not collaboration or collaboration.user_id != user_id or collaboration.status != CollaborationStatus.PENDING:
                return False
            
            update_data = {}
            if action == 'accept':
                update_data = {
                    'status': CollaborationStatus.ACCEPTED,
                    'accepted_at': datetime.now()
                }
            elif action == 'decline':
                update_data = {'status': CollaborationStatus.DECLINED}
            else:
                return False
            
            self.repo.update_collaboration(collaboration, update_data)
            return True
            
        except Exception as e:
            logger.error(f"Error responding to invitation: {str(e)}")
            return False

    def get_user_pending_invitations(self, user_id: int) -> List[AppCollaborator]:
        """Get all pending invitations for a user"""
        try:
            return self.repo.get_user_pending_invitations(user_id)
        except Exception as e:
            logger.error(f"Error getting pending invitations for user {user_id}: {str(e)}")
            return [] 