from typing import List, Optional, Tuple, Dict, Any
from model.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from model.app import App
from model.user import User
from extensions import db
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, or_
from utils.logger import get_logger
from utils.error_handlers import (
    handle_database_errors, NotFoundError, ValidationError, 
    validate_required_fields
)
from utils.database import safe_db_execute

logger = get_logger(__name__)


class AppCollaborationService:
    
    # ============================================================================
    # INVITATION MANAGEMENT
    # ============================================================================
    
    @staticmethod
    @handle_database_errors("invite_user_to_app")
    def invite_user_to_app(app_id: int, user_email: str, invited_by_user_id: int, role: CollaborationRole = CollaborationRole.EDITOR) -> Optional[AppCollaborator]:
        """
        Invite a user to collaborate on an app
        
        Args:
            app_id: ID of the app
            user_email: Email of the user to invite
            invited_by_user_id: ID of the user sending the invitation
            role: Role to assign to the invited user (default: EDITOR)
            
        Returns:
            AppCollaborator instance if invitation created successfully
        """
        # Validate inputs
        if not app_id or app_id <= 0:
            raise ValidationError("Invalid app_id")
        if not user_email or not user_email.strip():
            raise ValidationError("User email is required")
        if not invited_by_user_id or invited_by_user_id <= 0:
            raise ValidationError("Invalid inviter user_id")
        
        user_email = user_email.strip().lower()
        
        def invite_operation():
            # Check if app exists and inviter is the owner
            app = db.session.query(App).filter(App.app_id == app_id).first()
            if not app:
                raise NotFoundError(f"App with ID {app_id} not found", "app")
            
            if app.owner_id != invited_by_user_id:
                raise ValidationError("Only app owners can invite collaborators")
            
            # Find the user to invite
            user = db.session.query(User).filter(User.email == user_email).first()
            if not user:
                raise NotFoundError(f"User with email {user_email} not found", "user")
            
            # Check if user is already the owner
            if user.user_id == app.owner_id:
                raise ValidationError("Cannot invite the app owner as a collaborator")
            
            # Check if collaboration already exists
            existing_collab = db.session.query(AppCollaborator).filter(
                and_(
                    AppCollaborator.app_id == app_id,
                    AppCollaborator.user_id == user.user_id
                )
            ).first()
            
            if existing_collab:
                if existing_collab.status == CollaborationStatus.PENDING:
                    raise ValidationError(f"User {user_email} already has a pending invitation")
                elif existing_collab.status == CollaborationStatus.ACCEPTED:
                    raise ValidationError(f"User {user_email} is already a collaborator")
                else:  # DECLINED - allow re-invitation
                    existing_collab.status = CollaborationStatus.PENDING
                    existing_collab.role = role
                    existing_collab.invited_by = invited_by_user_id
                    existing_collab.invited_at = db.func.now()
                    existing_collab.accepted_at = None
                    db.session.commit()
                    logger.info(f"Re-invited user {user_email} to app {app_id}")
                    return existing_collab
            
            # Create new collaboration
            collaboration = AppCollaborator(
                app_id=app_id,
                user_id=user.user_id,
                role=role,
                invited_by=invited_by_user_id,
                status=CollaborationStatus.PENDING
            )
            
            db.session.add(collaboration)
            db.session.commit()
            db.session.refresh(collaboration)
            
            logger.info(f"Invited user {user_email} to app {app_id} with role {role.value}")
            return collaboration
        
        return safe_db_execute(invite_operation, "invite_user_to_app")
    
    @staticmethod
    @handle_database_errors("accept_invitation")
    def accept_invitation(collaboration_id: int, user_id: int) -> Optional[AppCollaborator]:
        """
        Accept a collaboration invitation
        
        Args:
            collaboration_id: ID of the collaboration invitation
            user_id: ID of the user accepting the invitation
            
        Returns:
            Updated AppCollaborator instance
        """
        if not collaboration_id or collaboration_id <= 0:
            raise ValidationError("Invalid collaboration_id")
        if not user_id or user_id <= 0:
            raise ValidationError("Invalid user_id")
        
        def accept_operation():
            collaboration = db.session.query(AppCollaborator).filter(
                and_(
                    AppCollaborator.id == collaboration_id,
                    AppCollaborator.user_id == user_id,
                    AppCollaborator.status == CollaborationStatus.PENDING
                )
            ).first()
            
            if not collaboration:
                raise NotFoundError("Invitation not found or already processed", "collaboration")
            
            collaboration.status = CollaborationStatus.ACCEPTED
            collaboration.accepted_at = db.func.now()
            
            db.session.commit()
            db.session.refresh(collaboration)
            
            logger.info(f"User {user_id} accepted invitation to app {collaboration.app_id}")
            return collaboration
        
        return safe_db_execute(accept_operation, "accept_invitation")
    
    @staticmethod
    @handle_database_errors("decline_invitation")
    def decline_invitation(collaboration_id: int, user_id: int) -> bool:
        """
        Decline a collaboration invitation
        
        Args:
            collaboration_id: ID of the collaboration invitation
            user_id: ID of the user declining the invitation
            
        Returns:
            True if invitation was declined successfully
        """
        if not collaboration_id or collaboration_id <= 0:
            raise ValidationError("Invalid collaboration_id")
        if not user_id or user_id <= 0:
            raise ValidationError("Invalid user_id")
        
        def decline_operation():
            collaboration = db.session.query(AppCollaborator).filter(
                and_(
                    AppCollaborator.id == collaboration_id,
                    AppCollaborator.user_id == user_id,
                    AppCollaborator.status == CollaborationStatus.PENDING
                )
            ).first()
            
            if not collaboration:
                raise NotFoundError("Invitation not found or already processed", "collaboration")
            
            collaboration.status = CollaborationStatus.DECLINED
            
            db.session.commit()
            
            logger.info(f"User {user_id} declined invitation to app {collaboration.app_id}")
            return True
        
        return safe_db_execute(decline_operation, "decline_invitation")
    
    @staticmethod
    @handle_database_errors("revoke_collaboration")
    def revoke_collaboration(app_id: int, user_id: int, revoked_by_user_id: int) -> bool:
        """
        Revoke a user's collaboration on an app (owner only)
        
        Args:
            app_id: ID of the app
            user_id: ID of the user to revoke
            revoked_by_user_id: ID of the user revoking the collaboration
            
        Returns:
            True if collaboration was revoked successfully
        """
        if not app_id or app_id <= 0:
            raise ValidationError("Invalid app_id")
        if not user_id or user_id <= 0:
            raise ValidationError("Invalid user_id")
        if not revoked_by_user_id or revoked_by_user_id <= 0:
            raise ValidationError("Invalid revoker user_id")
        
        def revoke_operation():
            # Check if revoker is the app owner
            app = db.session.query(App).filter(App.app_id == app_id).first()
            if not app:
                raise NotFoundError(f"App with ID {app_id} not found", "app")
            
            if app.owner_id != revoked_by_user_id:
                raise ValidationError("Only app owners can revoke collaborations")
            
            # Find the collaboration
            collaboration = db.session.query(AppCollaborator).filter(
                and_(
                    AppCollaborator.app_id == app_id,
                    AppCollaborator.user_id == user_id
                )
            ).first()
            
            if not collaboration:
                raise NotFoundError("Collaboration not found", "collaboration")
            
            # Delete the collaboration
            db.session.delete(collaboration)
            db.session.commit()
            
            logger.info(f"Revoked collaboration for user {user_id} on app {app_id}")
            return True
        
        return safe_db_execute(revoke_operation, "revoke_collaboration")
    
    @staticmethod
    @handle_database_errors("leave_app")
    def leave_app(app_id: int, user_id: int) -> bool:
        """
        Allow a user to leave an app (for collaborators only, not owners)
        
        Args:
            app_id: ID of the app
            user_id: ID of the user leaving the app
            
        Returns:
            True if user successfully left the app
        """
        if not app_id or app_id <= 0:
            raise ValidationError("Invalid app_id")
        if not user_id or user_id <= 0:
            raise ValidationError("Invalid user_id")
        
        def leave_operation():
            # Check if app exists
            app = db.session.query(App).filter(App.app_id == app_id).first()
            if not app:
                raise NotFoundError(f"App with ID {app_id} not found", "app")
            
            # Check if user is the owner (owners cannot leave their own app)
            if app.owner_id == user_id:
                raise ValidationError("App owners cannot leave their own app")
            
            # Find the collaboration
            collaboration = db.session.query(AppCollaborator).filter(
                and_(
                    AppCollaborator.app_id == app_id,
                    AppCollaborator.user_id == user_id,
                    AppCollaborator.status == CollaborationStatus.ACCEPTED
                )
            ).first()
            
            if not collaboration:
                raise NotFoundError("Collaboration not found or not accepted", "collaboration")
            
            # Delete the collaboration
            db.session.delete(collaboration)
            db.session.commit()
            
            logger.info(f"User {user_id} left app {app_id}")
            return True
        
        return safe_db_execute(leave_operation, "leave_app")
    
    # ============================================================================
    # QUERY OPERATIONS
    # ============================================================================
    
    @staticmethod
    @handle_database_errors("get_app_collaborators")
    def get_app_collaborators(app_id: int, status: Optional[CollaborationStatus] = None) -> List[AppCollaborator]:
        """
        Get all collaborators for an app
        
        Args:
            app_id: ID of the app
            status: Optional status filter
            
        Returns:
            List of AppCollaborator instances
        """
        if not app_id or app_id <= 0:
            return []
        
        def query_operation():
            query = db.session.query(AppCollaborator).options(
                joinedload(AppCollaborator.user),
                joinedload(AppCollaborator.inviter)
            ).filter(AppCollaborator.app_id == app_id)
            
            if status:
                query = query.filter(AppCollaborator.status == status)
            
            return query.all()
        
        try:
            collaborators = safe_db_execute(query_operation, "get_app_collaborators")
            logger.debug(f"Retrieved {len(collaborators)} collaborators for app {app_id}")
            return collaborators
        except Exception:
            logger.warning(f"Error getting collaborators for app {app_id}, returning empty list")
            return []
    
    @staticmethod
    @handle_database_errors("get_user_collaborations")
    def get_user_collaborations(user_id: int, status: Optional[CollaborationStatus] = None) -> List[AppCollaborator]:
        """
        Get all collaborations for a user
        
        Args:
            user_id: ID of the user
            status: Optional status filter
            
        Returns:
            List of AppCollaborator instances
        """
        if not user_id or user_id <= 0:
            return []
        
        def query_operation():
            query = db.session.query(AppCollaborator).options(
                joinedload(AppCollaborator.app),
                joinedload(AppCollaborator.inviter)
            ).filter(AppCollaborator.user_id == user_id)
            
            if status:
                query = query.filter(AppCollaborator.status == status)
            
            return query.all()
        
        try:
            collaborations = safe_db_execute(query_operation, "get_user_collaborations")
            logger.debug(f"Retrieved {len(collaborations)} collaborations for user {user_id}")
            return collaborations
        except Exception:
            logger.warning(f"Error getting collaborations for user {user_id}, returning empty list")
            return []
    
    @staticmethod
    @handle_database_errors("get_pending_invitations")
    def get_pending_invitations(user_id: int) -> List[AppCollaborator]:
        """
        Get pending invitations for a user
        
        Args:
            user_id: ID of the user
            
        Returns:
            List of pending AppCollaborator instances
        """
        return AppCollaborationService.get_user_collaborations(
            user_id, 
            status=CollaborationStatus.PENDING
        )
    
    @staticmethod
    @handle_database_errors("get_user_accessible_apps")
    def get_user_accessible_apps(user_id: int) -> List[App]:
        """
        Get all apps a user has access to (owned + collaborated)
        
        Args:
            user_id: ID of the user
            
        Returns:
            List of App instances
        """
        if not user_id or user_id <= 0:
            return []
        
        def query_operation():
            # Get owned apps
            owned_apps = db.session.query(App).filter(App.owner_id == user_id).all()
            
            # Get collaborated apps (accepted invitations only)
            collaborations = db.session.query(AppCollaborator).filter(
                and_(
                    AppCollaborator.user_id == user_id,
                    AppCollaborator.status == CollaborationStatus.ACCEPTED
                )
            ).options(joinedload(AppCollaborator.app)).all()
            
            collaborated_apps = [collab.app for collab in collaborations if collab.app]
            
            # Combine and remove duplicates
            all_apps = owned_apps + collaborated_apps
            unique_apps = list({app.app_id: app for app in all_apps}.values())
            
            return unique_apps
        
        try:
            apps = safe_db_execute(query_operation, "get_user_accessible_apps")
            logger.debug(f"User {user_id} has access to {len(apps)} apps")
            return apps
        except Exception:
            logger.warning(f"Error getting accessible apps for user {user_id}, returning empty list")
            return []
    
    # ============================================================================
    # PERMISSION CHECKING
    # ============================================================================
    
    @staticmethod
    @handle_database_errors("can_user_access_app")
    def can_user_access_app(user_id: int, app_id: int) -> bool:
        """
        Check if a user can access an app (owner or accepted collaborator)
        
        Args:
            user_id: ID of the user
            app_id: ID of the app
            
        Returns:
            True if user can access the app
        """
        if not user_id or user_id <= 0 or not app_id or app_id <= 0:
            return False
        
        def check_operation():
            # Check if user is the owner
            app = db.session.query(App).filter(App.app_id == app_id).first()
            if app and app.owner_id == user_id:
                return True
            
            # Check if user is an accepted collaborator
            collaboration = db.session.query(AppCollaborator).filter(
                and_(
                    AppCollaborator.app_id == app_id,
                    AppCollaborator.user_id == user_id,
                    AppCollaborator.status == CollaborationStatus.ACCEPTED
                )
            ).first()
            
            return collaboration is not None
        
        try:
            return safe_db_execute(check_operation, "can_user_access_app")
        except Exception:
            logger.warning(f"Error checking access for user {user_id} to app {app_id}, returning False")
            return False
    
    @staticmethod
    @handle_database_errors("can_user_manage_app")
    def can_user_manage_app(user_id: int, app_id: int) -> bool:
        """
        Check if a user can manage an app (owner only)
        
        Args:
            user_id: ID of the user
            app_id: ID of the app
            
        Returns:
            True if user can manage the app
        """
        if not user_id or user_id <= 0 or not app_id or app_id <= 0:
            return False
        
        def check_operation():
            app = db.session.query(App).filter(App.app_id == app_id).first()
            return app is not None and app.owner_id == user_id
        
        try:
            return safe_db_execute(check_operation, "can_user_manage_app")
        except Exception:
            logger.warning(f"Error checking management for user {user_id} to app {app_id}, returning False")
            return False
    
    @staticmethod
    @handle_database_errors("get_user_app_role")
    def get_user_app_role(user_id: int, app_id: int) -> Optional[CollaborationRole]:
        """
        Get the role of a user in an app
        
        Args:
            user_id: ID of the user
            app_id: ID of the app
            
        Returns:
            CollaborationRole or None if user has no access
        """
        if not user_id or user_id <= 0 or not app_id or app_id <= 0:
            return None
        
        def get_role_operation():
            # Check if user is the owner
            app = db.session.query(App).filter(App.app_id == app_id).first()
            if app and app.owner_id == user_id:
                return CollaborationRole.OWNER
            
            # Check if user is a collaborator
            collaboration = db.session.query(AppCollaborator).filter(
                and_(
                    AppCollaborator.app_id == app_id,
                    AppCollaborator.user_id == user_id,
                    AppCollaborator.status == CollaborationStatus.ACCEPTED
                )
            ).first()
            
            return collaboration.role if collaboration else None
        
        try:
            return safe_db_execute(get_role_operation, "get_user_app_role")
        except Exception:
            logger.warning(f"Error getting role for user {user_id} in app {app_id}, returning None")
            return None 