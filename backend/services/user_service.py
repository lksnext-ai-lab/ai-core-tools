from sqlalchemy.orm import Session
from sqlalchemy import select
from models.user import User, PlatformRole
from models.api_key import APIKey
from models.app import App
from repositories.user_repository import UserRepository
from repositories.app_repository import AppRepository
from repositories.app_collaboration_repository import AppCollaborationRepository
from services.user_deletion_errors import (
    OmniadminDeletionError,
    OwnedAppsPresentError,
    OwnedAppSummary,
    SelfDeletionError,
    UserNotFoundError,
)
from services.app_ownership_errors import TransferRecipientInvalidError, TierLimitExceededError
from typing import Literal, Optional, Tuple, List, Dict, Any
from utils.config import is_omniadmin, get_omniadmins
from utils.logger import get_logger

class UserService:

    @staticmethod
    def _user_to_dict(user: User, include_full_details: bool = True) -> Dict[str, Any]:
        """Convert a User ORM instance to a dict for API responses."""
        user_dict = {
            'user_id': user.user_id,
            'email': user.email,
            'name': user.name,
            'created_at': user.create_date.isoformat() if user.create_date else None,
        }

        if include_full_details:
            user_dict.update({
                'owned_apps_count': len(user.owned_apps) if user.owned_apps else 0,
                'api_keys_count': len(user.api_keys) if user.api_keys else 0,
                'is_active': user.is_active if hasattr(user, 'is_active') else True,
                'is_omniadmin': is_omniadmin(user.email),
                'platform_role': user.platform_role if user.platform_role else 'editor',
            })

        return user_dict

    @staticmethod
    def _get_user_or_raise(db: Session, user_id: int) -> User:
        """Return User by ID or raise ValueError if not found."""
        user_repo = UserRepository(db)
        user = user_repo.get_by_id(user_id)

        if not user:
            raise ValueError("User not found")

        return user

    @staticmethod
    def get_or_create_user(db: Session, email: str, name: str = None) -> Tuple[User, bool]:
        """Get existing user or create one. Returns (user, created)."""
        user_repo = UserRepository(db)

        user = user_repo.get_by_email(email)

        if user:
            user = user_repo.update(user, name)
            return user, False

        new_user = user_repo.create(email, name)
        return new_user, True

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User:
        """Get user by ID."""
        user_repo = UserRepository(db)
        return user_repo.get_by_id(user_id)

    @staticmethod
    def get_user_by_email(db: Session, email: str) -> User:
        """Get user by email."""
        user_repo = UserRepository(db)
        return user_repo.get_by_email(email)

    @staticmethod
    def get_user_accessible_apps(user_id: int):
        """Get all apps user has access to (owned + collaborated)."""
        # TODO: Implement this method
        pass

    @staticmethod
    def get_all_users(db: Session, page: int = 1, per_page: int = 10) -> Tuple[List[Dict], int]:
        """Get all users with pagination. Returns (users_list, total_count)."""
        user_repo = UserRepository(db)
        users, total = user_repo.get_all_paginated(page, per_page, exclude_emails=get_omniadmins())

        users_list = [UserService._user_to_dict(user) for user in users]

        return users_list, total

    @staticmethod
    def get_user_by_id_with_relations(db: Session, user_id: int) -> User:
        """Get user by ID with eagerly-loaded relations."""
        user_repo = UserRepository(db)
        return user_repo.get_by_id_with_relations(user_id)

    @staticmethod
    def search_users(db: Session, query: str, page: int = 1, per_page: int = 10) -> Tuple[List[Dict], int]:
        """Search users by name or email. Returns (users_list, total_count)."""
        user_repo = UserRepository(db)
        users, total = user_repo.search_users(query, page, per_page, exclude_emails=get_omniadmins())

        users_list = [UserService._user_to_dict(user) for user in users]

        return users_list, total

    @staticmethod
    def delete_user(
        db: Session,
        user_id: int,
        *,
        actor_user_id: int,
        mode: Literal["block", "cascade_apps", "transfer_apps"] = "block",
        transfer_to_user_id: Optional[int] = None,
    ) -> bool:
        """Delete a user with ordered, safe orchestration.

        Deletion taxonomy (AD-1):
        - Class A (credentials, tokens, subscription): DB ON DELETE CASCADE.
        - Class B (owned apps): explicit via AppService.delete_app (cascade) or
          AppOwnershipService._reassign_owner (transfer).
        - Class C (collaborations, API keys in non-owned apps): explicit here.
        - Class D (invited_by, Conversation.user_id, etc.): DB ON DELETE SET NULL.

        Atomicity (AD-2): ``transfer_apps`` runs all reassignments plus the user
        deletion in one transaction. ``cascade_apps`` commits per-app; user deletion
        is last so a mid-failure leaves the user intact with remaining apps (resumable).

        Args:
            db: Synchronous SQLAlchemy session.
            user_id: PK of the user to delete.
            actor_user_id: PK of the administrator performing the action.
            mode: ``'block'`` rejects if user owns apps; ``'cascade_apps'`` deletes
                them; ``'transfer_apps'`` reassigns them to ``transfer_to_user_id``.
            transfer_to_user_id: Required for ``mode='transfer_apps'``.

        Returns:
            ``True`` on successful deletion.

        Raises:
            UserNotFoundError: Target not found (→ 404).
            SelfDeletionError: Actor equals target (→ 400).
            OmniadminDeletionError: Target is an omniadmin (→ 403).
            OwnedAppsPresentError: User owns apps and mode='block' (→ 409).
        """
        # Lazy import — avoids circular dependency (app_service → child services → user_service).
        from services.app_service import AppService

        logger = get_logger(__name__)

        # Acquire row lock on the target user (AD-6 — serialises concurrent delete requests).
        user: Optional[User] = db.execute(
            select(User).where(User.user_id == user_id).with_for_update()
        ).scalar_one_or_none()

        if user is None:
            logger.warning(
                f"delete_user: target not found — user_id={user_id}, actor_user_id={actor_user_id}"
            )
            raise UserNotFoundError(user_id)

        # Read email now: per-app commits in cascade_apps expire the ORM instance
        # (expire_on_commit=True), so a later attribute read would trigger a reload.
        user_email: str = user.email

        if actor_user_id == user_id:
            logger.warning(
                f"delete_user: self-deletion rejected — user_id={user_id}, actor_user_id={actor_user_id}"
            )
            raise SelfDeletionError(user_id)

        if is_omniadmin(user_email):
            logger.warning(
                f"delete_user: omniadmin deletion rejected — user_id={user_id}, actor_user_id={actor_user_id}"
            )
            raise OmniadminDeletionError(user_email)

        # Emit start log AFTER guardrails — rejected requests must not appear as
        # initiated deletions in the audit trail (NFR-6).
        logger.info(
            f"delete_user: start — user_id={user_id} mode={mode} actor_user_id={actor_user_id}"
        )

        app_repo = AppRepository(db)
        owned_apps = app_repo.get_by_owner(user_id)

        if owned_apps:
            owned_app_summaries: List[OwnedAppSummary] = [
                {"app_id": app.app_id, "name": app.name} for app in owned_apps
            ]

            if mode == "block":
                logger.warning(
                    f"delete_user: owned-apps-present block — user_id={user_id} "
                    f"owned_app_count={len(owned_apps)} actor_user_id={actor_user_id}"
                )
                raise OwnedAppsPresentError(owned_app_summaries)

            if mode == "transfer_apps":
                # AD-2: all reassignments + user deletion are one atomic transaction.
                # Call _reassign_owner directly (NOT transfer_direct, which commits).
                if transfer_to_user_id is None:
                    raise TransferRecipientInvalidError(
                        "transfer_to_user_id must be provided when mode='transfer_apps'."
                    )

                if transfer_to_user_id == user_id:
                    raise TransferRecipientInvalidError(
                        "transfer_to_user_id cannot be the same user that is being deleted."
                    )

                # Validate recipient once up front before touching any App row.
                recipient = db.execute(
                    select(User).where(User.user_id == transfer_to_user_id)
                ).scalar_one_or_none()

                if recipient is None:
                    raise TransferRecipientInvalidError(
                        f"User {transfer_to_user_id} does not exist."
                    )

                if not recipient.is_active:
                    raise TransferRecipientInvalidError(
                        f"User {transfer_to_user_id} is not active and cannot receive app ownership."
                    )

                from services.app_ownership_service import AppOwnershipService

                # Re-fetch with row locks (AD-6) — the initial get_by_owner held no lock;
                # _reassign_owner mutates owner_id so concurrent transfer_direct could race.
                locked_owned_apps = db.execute(
                    select(App).where(App.owner_id == user_id).with_for_update()
                ).scalars().all()

                try:
                    for app in locked_owned_apps:
                        logger.info(
                            f"delete_user(transfer_apps): staging transfer of app_id={app.app_id} "
                            f"'{app.name}' to user_id={transfer_to_user_id} for user_id={user_id}"
                        )
                        AppOwnershipService._reassign_owner(
                            db,
                            app,
                            transfer_to_user_id,
                            actor_user_id=actor_user_id,
                        )
                except Exception:
                    db.rollback()
                    logger.error(
                        f"delete_user(transfer_apps): rollback — staged transfers reverted "
                        f"for user_id={user_id} recipient={transfer_to_user_id} actor_user_id={actor_user_id}",
                        exc_info=True,
                    )
                    raise

            if mode == "cascade_apps":
                # cascade_apps commits per-app. Delete user LAST so a failure mid-loop
                # leaves the user intact with remaining owned apps (resumable — AD-2/AC-13).
                app_svc = AppService(db)
                for app in owned_apps:
                    app_id_to_delete = app.app_id
                    app_name = app.name
                    logger.info(
                        f"delete_user(cascade_apps): deleting owned app {app_id_to_delete} "
                        f"'{app_name}' for user_id={user_id}"
                    )
                    success = app_svc.delete_app(app_id_to_delete)
                    if not success:
                        # False means "already gone" OR "failed mid-cascade". Distinguish:
                        # if the app still exists this was a real failure — abort before
                        # db.delete(user) to avoid orphaning the app.
                        if app_repo.get_by_id(app_id_to_delete) is not None:
                            logger.error(
                                f"delete_user(cascade_apps): delete_app failed for "
                                f"app_id={app_id_to_delete}; aborting before user deletion "
                                f"to avoid orphaning the app."
                            )
                            raise RuntimeError(
                                f"Failed to delete owned app {app_id_to_delete} during "
                                f"cascade deletion of user {user_id}."
                            )
                        logger.warning(
                            f"delete_user(cascade_apps): app_id={app_id_to_delete} already "
                            f"absent — treating as concurrently removed and continuing"
                        )

        try:
            # Re-acquire the row lock. cascade_apps per-app commits released the entry
            # lock and expired `user`; re-locking prevents a delete-races-mutation window.
            user = db.execute(
                select(User).where(User.user_id == user_id).with_for_update()
            ).scalar_one_or_none()
            if user is None:
                raise UserNotFoundError(user_id)

            # Class C: remove collaboration memberships.
            collab_repo = AppCollaborationRepository(db)
            memberships = collab_repo.get_collaborations_by_user(user_id)
            for membership in memberships:
                logger.info(
                    f"delete_user: removing collaboration id={membership.id} "
                    f"app_id={membership.app_id} user_id={user_id}"
                )
                db.delete(membership)

            db.flush()

            # Class C: remove surviving API keys (owned-app keys already removed by
            # delete_app; this catches keys held in other apps).
            surviving_keys = db.execute(
                select(APIKey).where(APIKey.user_id == user_id)
            ).scalars().all()
            for api_key in surviving_keys:
                logger.info(
                    f"delete_user: removing APIKey key_id={api_key.key_id} "
                    f"app_id={api_key.app_id} user_id={user_id}"
                )
                db.delete(api_key)

            db.flush()

            # Class A (credentials, tokens, subscription) handled by DB ON DELETE CASCADE.
            # Class D (invited_by, Conversation.user_id, etc.) handled by DB ON DELETE SET NULL.
            # passive_deletes=True on all mapped relationships prevents ORM interference.
            db.delete(user)
            db.commit()

            logger.info(
                f"delete_user: complete — user_id={user_id} mode={mode} actor_user_id={actor_user_id}"
            )
            return True

        except Exception:
            db.rollback()
            logger.error(
                f"delete_user: rollback — user_id={user_id} mode={mode} "
                f"actor_user_id={actor_user_id}",
                exc_info=True,
            )
            raise

    @staticmethod
    def get_user_stats(db: Session) -> Dict[str, Any]:
        """Get system-wide user statistics."""
        user_repo = UserRepository(db)

        total_users = user_repo.get_total_count()
        recent_users = user_repo.get_recent_users_count(30)
        users_with_apps = user_repo.get_users_with_apps_count()
        recent_users_list = user_repo.get_recent_users_list(30, 10)

        recent_users_data = [
            UserService._user_to_dict(user, include_full_details=False)
            for user in recent_users_list
        ]

        return {
            'total_users': total_users,
            'recent_users': recent_users,
            'users_with_apps': users_with_apps,
            'recent_users_list': recent_users_data
        }

    @staticmethod
    def activate_user(db: Session, user_id: int, admin_email: str) -> User:
        """Activate a user account.

        Raises:
            ValueError: If user is already active.
        """
        logger = get_logger(__name__)
        user = UserService._get_user_or_raise(db, user_id)

        if user.is_active:
            raise ValueError("User is already active")

        user.is_active = True
        db.commit()
        db.refresh(user)

        logger.info(f"User activated - Admin: {admin_email}, Target User: {user.email} (ID: {user_id})")

        return user

    @staticmethod
    def deactivate_user(db: Session, user_id: int, admin_email: str) -> User:
        """Deactivate a user account.

        Raises:
            ValueError: If user is already inactive, is an omniadmin, or is the acting admin.
        """
        logger = get_logger(__name__)
        user = UserService._get_user_or_raise(db, user_id)

        if not user.is_active:
            raise ValueError("User is already inactive")

        if is_omniadmin(user.email):
            raise ValueError("Cannot deactivate admin users")

        if user.email == admin_email:
            raise ValueError("Cannot deactivate your own account")

        user.is_active = False
        db.commit()
        db.refresh(user)

        logger.info(f"User deactivated - Admin: {admin_email}, Target User: {user.email} (ID: {user_id})")

        return user

    @staticmethod
    def set_platform_role(db: Session, user_id: int, role: str, admin_email: str) -> dict:
        from models.app import App
        logger = get_logger(__name__)
        valid_roles = {r.value for r in PlatformRole}
        if role not in valid_roles:
            raise ValueError(f"Invalid platform role '{role}'. Must be one of: {', '.join(valid_roles)}")

        user = UserService._get_user_or_raise(db, user_id)

        if is_omniadmin(user.email):
            raise PermissionError("Cannot change the platform role of an omniadmin user")

        if user.email == admin_email:
            raise ValueError("Cannot change your own platform role")

        user.platform_role = role
        db.commit()
        db.refresh(user)

        logger.info(f"Platform role set to '{role}' - Admin: {admin_email}, Target: {user.email} (ID: {user_id})")

        warnings: List[str] = []
        if role == 'viewer':
            owned = db.query(App).filter(App.owner_id == user_id).count()
            if owned:
                warnings.append(f"User owns {owned} app(s). They retain ownership but cannot modify them while a viewer.")

        return {"user": user, "warnings": warnings}

    @staticmethod
    def get_active_users_count(db: Session) -> int:
        """Get count of active users."""
        return db.query(User).filter(User.is_active == True).count()

    @staticmethod
    def get_inactive_users_count(db: Session) -> int:
        """Get count of inactive users."""
        return db.query(User).filter(User.is_active == False).count()
