from typing import List, Optional
from sqlalchemy.orm import Session
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from models.app import App
from repositories.app_collaboration_repository import AppCollaborationRepository
from repositories.app_repository import AppRepository
from utils.logger import get_logger
from datetime import datetime
from sqlalchemy.exc import IntegrityError

logger = get_logger(__name__)

class AppCollaborationService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = AppCollaborationRepository(db)

    def get_user_accessible_apps(self, user_id: int) -> List[App]:
        """Get all apps that a user can access (owned + collaborated)."""
        return self.repo.get_user_accessible_apps(user_id)

    def can_user_manage_app(self, user_id: int, app_id: int) -> bool:
        """Check if user can manage an app (owner only)."""
        return self.repo.can_user_manage_app(user_id, app_id)

    def can_user_manage_collaborators(self, user_id: int, app_id: int) -> bool:
        """Check if user can manage collaborators (owner only)."""
        return self.repo.can_user_manage_collaborators(user_id, app_id)

    def can_user_administer_app(self, user_id: int, app_id: int) -> bool:
        """Check if user can administer an app (owner or administrator)."""
        return self.repo.can_user_administer_app(user_id, app_id)

    def can_user_access_app(self, user_id: int, app_id: int) -> bool:
        """Check if user can access an app (owner or accepted collaborator)."""
        return self.repo.can_user_access_app(user_id, app_id)

    def get_user_app_role(self, user_id: int, app_id: int) -> Optional[str]:
        """Get the role of a user in an app."""
        if not user_id or user_id <= 0 or not app_id or app_id <= 0:
            return None

        try:
            return self.repo.get_user_app_role(user_id, app_id)
        except Exception as e:
            logger.warning(f"Error getting role for user {user_id} in app {app_id}: {str(e)}")
            return None

    def get_app_collaborators(self, app_id: int) -> List[AppCollaborator]:
        """Get all collaborators for an app."""
        return self.repo.get_app_collaborators(app_id)

    def invite_user_to_app(self, app_id: int, user_email: str, invited_by_user_id: int, role: str = "editor") -> Optional[AppCollaborator]:
        """Invite a user to collaborate on an app."""
        try:
            if not self.repo.can_user_administer_app(invited_by_user_id, app_id):
                raise ValueError("Only app owners or administrators can invite collaborators")

            user = self.repo.get_user_by_email(user_email)
            if not user:
                raise ValueError(f"User with email {user_email} not found")

            if self.repo.can_user_manage_app(user.user_id, app_id):
                raise ValueError("Cannot invite the app owner as a collaborator")

            existing_collab = self.repo.get_membership_by_app_and_user(app_id, user.user_id)

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

            from services.tier_enforcement_service import TierEnforcementService
            TierEnforcementService.check_resource_limit(self.db, app_id, 'collaborators')

            collaboration_data = {
                'app_id': app_id,
                'user_id': user.user_id,
                'role': CollaborationRole(role.lower()),
                'invited_by': invited_by_user_id,
                'status': CollaborationStatus.PENDING
            }

            try:
                collaboration = self.repo.create_collaboration(collaboration_data)
            except IntegrityError:
                self.db.rollback()
                existing_collab = self.repo.get_membership_by_app_and_user(app_id, user.user_id)
                if existing_collab is None:
                    raise
                if existing_collab.status == CollaborationStatus.PENDING:
                    raise ValueError(f"User {user_email} already has a pending invitation")
                if existing_collab.status == CollaborationStatus.ACCEPTED:
                    raise ValueError(f"User {user_email} is already a collaborator")
                return self.repo.update_collaboration(existing_collab, {
                    'status': CollaborationStatus.PENDING,
                    'role': CollaborationRole(role.lower()),
                    'invited_by': invited_by_user_id,
                    'invited_at': datetime.now(),
                    'accepted_at': None,
                })

            logger.info(f"Invited user {user_email} to app {app_id} with role {role}")
            return collaboration

        except Exception as e:
            logger.error(f"Error inviting user {user_email} to app {app_id}: {str(e)}")
            raise

    def update_collaborator_role(self, app_id: int, user_id: int, new_role: str, updated_by_user_id: int) -> bool:
        """Update a collaborator's role."""
        try:
            if not self.repo.can_user_manage_app(updated_by_user_id, app_id):
                raise ValueError("Only app owners can update collaborator roles")

            collaboration = self.repo.get_membership_by_app_and_user(app_id, user_id)
            if not collaboration:
                raise ValueError("Collaboration not found")

            if collaboration.status != CollaborationStatus.ACCEPTED:
                raise ValueError("Can only update roles for accepted collaborations")

            update_data = {'role': CollaborationRole(new_role.lower())}
            self.repo.update_collaboration(collaboration, update_data)

            logger.info(f"Updated role for user {user_id} in app {app_id} to {new_role}")
            return True

        except Exception as e:
            logger.error(f"Error updating role for user {user_id} in app {app_id}: {str(e)}")
            raise

    def _delete_collaboration_with_chat_cleanup(self, collaboration, app_id: int, user_id: int) -> bool:
        """Delete the collaboration and the user's App Chat data of THAT App (same stage / finish as user deletion).

        The user's Chat conversation rows go in the same transaction as the collaboration (commit ordering as in user
        deletion); their threads, files, temp silo / vectors and sandboxes are removed after the commit, best effort
        (a failure is logged by class name and never fails the removal). Other members' data and the same user's
        data in other Apps are untouched.
        """
        from services.internal_chat.user_cleanup import (
            finish_user_chat_conversations,
            stage_user_chat_conversations,
        )

        staged = []
        try:
            staged = stage_user_chat_conversations(self.db, user_id, app_id=app_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not stage the chat cleanup of user %s in app %s (%s)", user_id, app_id, type(exc).__name__)
            self.db.rollback()
        success = self.repo.delete_collaboration(collaboration)
        if success and staged:
            finish_user_chat_conversations(self.db, user_id, staged)  # best effort, never raises
        return success

    def remove_collaborator(self, app_id: int, user_id: int, removed_by_user_id: int) -> bool:
        """Remove a collaborator from an app."""
        try:
            if not self.repo.can_user_manage_app(removed_by_user_id, app_id):
                raise ValueError("Only app owners can remove collaborators")

            collaboration = self.repo.get_membership_by_app_and_user(app_id, user_id)
            if not collaboration:
                raise ValueError("Collaboration not found")

            success = self._delete_collaboration_with_chat_cleanup(collaboration, app_id, user_id)

            if success:
                logger.info(f"Removed user {user_id} from app {app_id}")

            return success

        except Exception as e:
            logger.error(f"Error removing user {user_id} from app {app_id}: {str(e)}")
            raise

    def grant_access_directly(
        self,
        app_id: int,
        user_id: int,
        role: str,
        granted_by_user_id: int,
    ) -> Optional[AppCollaborator]:
        """Grant accepted app access for an already-existing platform user."""
        app = AppRepository(self.db).get_by_id(app_id)
        user = self.repo.get_user_by_id(user_id)
        if app is None or user is None:
            return None
        if app.owner_id == user_id:
            raise ValueError("The app owner already has access and cannot be changed here.")
        if user.platform_role == "viewer" and role.lower() != "viewer":
            raise ValueError("Users with viewer platform role can only be assigned the viewer app role.")

        now = datetime.now()
        update_data = {
            "role": CollaborationRole(role.lower()),
            "invited_by": granted_by_user_id,
            "invited_at": now,
            "accepted_at": now,
            "status": CollaborationStatus.ACCEPTED,
        }
        collaboration = self.repo.get_membership_by_app_and_user(app_id, user_id)
        if collaboration is not None:
            return self.repo.update_collaboration(collaboration, update_data)

        try:
            return self.repo.create_collaboration({
                **update_data,
                "app_id": app_id,
                "user_id": user_id,
            })
        except IntegrityError:
            self.db.rollback()
            collaboration = self.repo.get_membership_by_app_and_user(app_id, user_id)
            if collaboration is None:
                raise
            return self.repo.update_collaboration(collaboration, update_data)

    def remove_user_access_directly(self, app_id: int, user_id: int) -> bool:
        """Remove collaborator access without changing app ownership."""
        app = AppRepository(self.db).get_by_id(app_id)
        if app is None:
            return False
        if app.owner_id == user_id:
            raise ValueError("App ownership cannot be removed here.")

        return self.repo.delete_user_collaborations(app_id, user_id) > 0

    def leave_app_collaboration(self, app_id: int, user_id: int) -> bool:
        """Allow a collaborator to leave an app collaboration themselves."""
        try:
            collaboration = self.repo.get_collaboration_by_app_and_user(app_id, user_id)
            if not collaboration:
                raise ValueError("Collaboration not found")

            if self.repo.can_user_manage_app(user_id, app_id):
                raise ValueError("App owners cannot leave their own apps")

            if collaboration.status != CollaborationStatus.ACCEPTED:
                raise ValueError("Can only leave accepted collaborations")

            success = self._delete_collaboration_with_chat_cleanup(collaboration, app_id, user_id)

            if success:
                logger.info(f"User {user_id} left app {app_id}")

            return success

        except Exception as e:
            logger.error(f"Error leaving app {app_id} for user {user_id}: {str(e)}")
            raise

    def _get_pending_invitation(
        self,
        invitation_id: int,
        user_id: int,
    ) -> Optional[AppCollaborator]:
        collaboration = self.repo.get_collaboration_by_id(invitation_id)
        if collaboration is None:
            logger.warning(f"Invitation {invitation_id} not found")
            return None
        if int(collaboration.user_id) != int(user_id):
            logger.warning(
                f"Invitation {invitation_id} belongs to user {collaboration.user_id}, not {user_id}"
            )
            return None
        if collaboration.status != CollaborationStatus.PENDING:
            logger.warning(
                f"Invitation {invitation_id} status is {collaboration.status}, not PENDING"
            )
            return None
        return collaboration

    def _respond_to_ownership_offer(
        self,
        invitation_id: int,
        user_id: int,
        action: str,
    ) -> bool:
        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import (
            NotOfferRecipientError,
            OwnershipOfferNotFoundError,
        )

        if action not in {"accept", "decline"}:
            logger.warning(
                f"Invalid action '{action}' for ownership offer {invitation_id}"
            )
            return False

        try:
            if action == "accept":
                AppOwnershipService.accept(
                    self.db, invitation_id, actor_user_id=user_id
                )
            else:
                AppOwnershipService.decline(
                    self.db, invitation_id, actor_user_id=user_id
                )
            return True
        except (OwnershipOfferNotFoundError, NotOfferRecipientError) as exc:
            logger.warning(
                f"respond_to_invitation: ownership {action} rejected "
                f"invitation_id={invitation_id} user_id={user_id} — {exc}"
            )
            return False

    @staticmethod
    def _invitation_response_update(action: str) -> Optional[dict]:
        if action == "accept":
            return {
                "status": CollaborationStatus.ACCEPTED,
                "accepted_at": datetime.now(),
            }
        if action == "decline":
            return {"status": CollaborationStatus.DECLINED}
        return None

    def respond_to_invitation(self, invitation_id: int, user_id: int, action: str) -> bool:
        """Respond to an invitation or ownership offer as its intended recipient."""
        try:
            collaboration = self._get_pending_invitation(invitation_id, user_id)
            if collaboration is None:
                return False

            if collaboration.role == CollaborationRole.OWNER:
                return self._respond_to_ownership_offer(
                    invitation_id, user_id, action
                )

            update_data = self._invitation_response_update(action)
            if update_data is None:
                logger.warning(f"Invalid action {action} for invitation {invitation_id}")
                return False

            self.repo.update_collaboration(collaboration, update_data)
            return True
        except Exception as e:
            logger.error(f"Error responding to invitation: {str(e)}")
            return False

    def get_user_pending_invitations(self, user_id: int) -> List[AppCollaborator]:
        """Get all pending invitations for a user."""
        try:
            return self.repo.get_user_pending_invitations(user_id)
        except Exception as e:
            logger.error(f"Error getting pending invitations for user {user_id}: {str(e)}")
            return []
