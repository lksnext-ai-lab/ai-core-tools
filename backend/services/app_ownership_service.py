"""App ownership transfer service — single source of truth for all App.owner_id reassignment."""
from __future__ import annotations

from datetime import datetime
from typing import Tuple

from fastapi import HTTPException as _HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from models.app import App
from models.user import User
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from repositories.app_collaboration_repository import AppCollaborationRepository
from services.app_ownership_errors import (
    AppNotFoundError,
    NotOfferRecipientError,
    OwnershipOfferNotFoundError,
    TierLimitExceededError,
    TransferRecipientInvalidError,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class AppOwnershipService:
    """Service for app ownership transfer — administrative-direct and voluntary paths."""

    @staticmethod
    def _reassign_owner(
        db: Session,
        app: App,
        new_owner_id: int,
        *,
        actor_user_id: int,
    ) -> None:
        """Stage the owner reassignment for ``app`` onto ``new_owner_id``.

        Never calls ``db.commit()`` — the caller owns the transaction boundary.
        Enforces: recipient validity, tier limit (SaaS), owner_id staging, and
        collaborator-row hygiene (ownership supersedes collaboration — FR-C5).

        Raises:
            TransferRecipientInvalidError: Recipient does not exist, is inactive, or is already owner.
            TierLimitExceededError: Transfer would exceed new owner's SaaS app-count limit.
        """
        recipient: User | None = db.execute(
            select(User).where(User.user_id == new_owner_id)
        ).scalar_one_or_none()

        if recipient is None:
            raise TransferRecipientInvalidError(
                f"User {new_owner_id} does not exist."
            )

        if not recipient.is_active:
            raise TransferRecipientInvalidError(
                f"User {new_owner_id} is not active and cannot receive app ownership."
            )

        if app.owner_id == new_owner_id:
            raise TransferRecipientInvalidError(
                f"User {new_owner_id} is already the owner of app {app.app_id}."
            )

        # Flush first so prior staged owner_id changes in the same transaction are
        # visible to the tier COUNT (autoflush=False session; avoids off-by-one in
        # multi-app transfer loops).
        db.flush()

        from services.tier_enforcement_service import TierEnforcementService  # noqa: PLC0415 — circular-safe lazy import

        try:
            TierEnforcementService.check_app_limit(db, new_owner_id)
        except _HTTPException as tier_exc:
            raise TierLimitExceededError(new_owner_id, tier_exc.detail)

        app.owner_id = new_owner_id

        # Remove any pre-existing collaborator row for the new owner (FR-C5).
        collab_repo = AppCollaborationRepository(db)
        existing_collab: AppCollaborator | None = (
            collab_repo.get_collaboration_by_app_and_user(app.app_id, new_owner_id)
        )
        if existing_collab is not None:
            logger.info(
                f"transfer_owner: removing pre-existing collaborator row "
                f"collab_id={existing_collab.id} app_id={app.app_id} "
                f"user_id={new_owner_id} actor_user_id={actor_user_id}"
            )
            db.delete(existing_collab)

        logger.info(
            f"transfer_owner: staged owner_id={new_owner_id} for app_id={app.app_id} "
            f"actor_user_id={actor_user_id}"
        )

    @staticmethod
    def transfer_direct(
        db: Session,
        app_id: int,
        new_owner_id: int,
        *,
        actor_user_id: int,
    ) -> Tuple[App, int]:
        """Reassign ``app_id`` to ``new_owner_id`` immediately (no handshake).

        Administrative-direct path (FR-C1/FR-C3). Owns its own commit; do NOT
        call this inside the ``delete_user(transfer_apps)`` loop — use
        ``_reassign_owner`` directly to keep the loop atomic.

        Post-commit: ``FreezeService.apply_freeze`` is called best-effort for the
        new owner (FR-C7). A failure there never reverts the committed transfer.

        Returns:
            ``(app, previous_owner_id)`` — refreshed App and former owner PK.

        Raises:
            AppNotFoundError: app_id not found (→ 404).
            TransferRecipientInvalidError: Recipient validation failed (→ 400).
            TierLimitExceededError: SaaS tier limit exceeded (→ 409).
        """
        logger.info(
            f"transfer_direct: start app_id={app_id} new_owner_id={new_owner_id} "
            f"actor_user_id={actor_user_id}"
        )

        app: App | None = db.execute(
            select(App).where(App.app_id == app_id).with_for_update()
        ).scalar_one_or_none()

        if app is None:
            raise AppNotFoundError(app_id)

        previous_owner_id: int = app.owner_id

        try:
            AppOwnershipService._reassign_owner(
                db, app, new_owner_id, actor_user_id=actor_user_id
            )
            db.commit()
            db.refresh(app)
        except Exception:
            db.rollback()
            logger.error(
                f"transfer_direct: rollback app_id={app_id} new_owner_id={new_owner_id} "
                f"actor_user_id={actor_user_id}",
                exc_info=True,
            )
            raise

        logger.info(
            f"transfer_direct: complete app_id={app_id} "
            f"previous_owner_id={previous_owner_id} new_owner_id={new_owner_id} "
            f"actor_user_id={actor_user_id}"
        )

        # FR-C7: best-effort freeze re-evaluation for the new owner after commit.
        # Failure must never revert the committed transfer — rollback only the freeze.
        try:
            from services.freeze_service import FreezeService
            from deployment_mode import is_self_managed

            if not is_self_managed():
                from repositories.subscription_repository import SubscriptionRepository

                sub_repo = SubscriptionRepository(db)
                sub = sub_repo.get_by_user_id(new_owner_id)
                if sub:
                    effective_tier = sub.admin_override_tier or (
                        sub.tier.value if sub.tier else "free"
                    )
                    FreezeService.apply_freeze(db, new_owner_id, effective_tier)
                    db.commit()
        except Exception as freeze_exc:
            db.rollback()
            logger.warning(
                f"transfer_direct: FreezeService post-commit re-eval failed for "
                f"new_owner_id={new_owner_id} app_id={app_id} — {freeze_exc}. "
                f"Transfer is committed; freeze state may need manual recalculation."
            )

        return app, previous_owner_id

    @staticmethod
    def offer(
        db: Session,
        app_id: int,
        new_owner_id: int,
        *,
        actor_user_id: int,
    ) -> AppCollaborator:
        """Create or refresh a pending ownership offer.

        Modelled as ``AppCollaborator(role=OWNER, status=PENDING)`` (AD-5 — no new
        migration). The offer grants no access until ``accept`` flips ``App.owner_id``.
        Idempotent: refreshes an existing offer for the same recipient rather than
        duplicating. Supersedes any prior pending offer to a different recipient.

        Raises:
            AppNotFoundError: app_id not found (→ 404).
            TransferRecipientInvalidError: Recipient invalid (→ 400).
        """
        logger.info(
            f"offer: start app_id={app_id} new_owner_id={new_owner_id} "
            f"actor_user_id={actor_user_id}"
        )

        app: App | None = db.execute(
            select(App).where(App.app_id == app_id).with_for_update()
        ).scalar_one_or_none()

        if app is None:
            raise AppNotFoundError(app_id)

        recipient: User | None = db.execute(
            select(User).where(User.user_id == new_owner_id)
        ).scalar_one_or_none()

        if recipient is None:
            raise TransferRecipientInvalidError(
                f"User {new_owner_id} does not exist."
            )

        if not recipient.is_active:
            raise TransferRecipientInvalidError(
                f"User {new_owner_id} is not active and cannot receive app ownership."
            )

        if app.owner_id == new_owner_id:
            raise TransferRecipientInvalidError(
                f"User {new_owner_id} is already the owner of app {app_id}."
            )

        try:
            # Load all pending OWNER offers under a lock. Refresh the one for this
            # recipient (idempotent); delete any offer for a different recipient so
            # cancel/accept never face competing rows.
            existing_offers = db.execute(
                select(AppCollaborator)
                .where(
                    AppCollaborator.app_id == app_id,
                    AppCollaborator.role == CollaborationRole.OWNER,
                    AppCollaborator.status == CollaborationStatus.PENDING,
                )
                .with_for_update()
            ).scalars().all()

            same_recipient_offer: AppCollaborator | None = None
            for off in existing_offers:
                if int(off.user_id) == int(new_owner_id):
                    same_recipient_offer = off
                else:
                    db.delete(off)
                    logger.info(
                        f"offer: superseded prior PENDING OWNER offer collab_id={off.id} "
                        f"app_id={app_id} prior_recipient={off.user_id} actor_user_id={actor_user_id}"
                    )

            if same_recipient_offer is not None:
                same_recipient_offer.status = CollaborationStatus.PENDING
                same_recipient_offer.invited_by = actor_user_id
                same_recipient_offer.invited_at = datetime.now()
                same_recipient_offer.accepted_at = None
                db.add(same_recipient_offer)
                db.commit()
                db.refresh(same_recipient_offer)
                offer_row = same_recipient_offer
                logger.info(
                    f"offer: refreshed existing PENDING OWNER row collab_id={same_recipient_offer.id} "
                    f"app_id={app_id} new_owner_id={new_owner_id} actor_user_id={actor_user_id}"
                )
            else:
                new_collab = AppCollaborator(
                    app_id=app_id,
                    user_id=new_owner_id,
                    role=CollaborationRole.OWNER,
                    status=CollaborationStatus.PENDING,
                    invited_by=actor_user_id,
                    invited_at=datetime.now(),
                )
                db.add(new_collab)
                db.commit()
                db.refresh(new_collab)
                offer_row = new_collab
                logger.info(
                    f"offer: created PENDING OWNER row collab_id={new_collab.id} "
                    f"app_id={app_id} new_owner_id={new_owner_id} actor_user_id={actor_user_id}"
                )
        except Exception:
            db.rollback()
            logger.error(
                f"offer: rollback app_id={app_id} new_owner_id={new_owner_id} "
                f"actor_user_id={actor_user_id}",
                exc_info=True,
            )
            raise

        return offer_row

    @staticmethod
    def accept(
        db: Session,
        collaboration_id: int,
        *,
        actor_user_id: int,
        app_id: int | None = None,
    ) -> Tuple[App, int]:
        """Accept a pending ownership offer (recipient only).

        Calls ``_reassign_owner`` (validates, checks tier, stages owner_id, removes
        the offer row via collaborator hygiene). Demotes the previous owner to
        ADMINISTRATOR/ACCEPTED so they retain access (FR-D3). Single transaction.

        Returns:
            ``(app, previous_owner_id)``.

        Raises:
            OwnershipOfferNotFoundError: Offer not found or not PENDING OWNER (→ 404).
            NotOfferRecipientError: Actor is not the named recipient (→ 403).
            TransferRecipientInvalidError: Recipient validation failed (→ 400).
            TierLimitExceededError: Tier limit exceeded (→ 409).
        """
        logger.info(
            f"accept: start collaboration_id={collaboration_id} actor_user_id={actor_user_id}"
        )

        offer: AppCollaborator | None = db.execute(
            select(AppCollaborator)
            .where(AppCollaborator.id == collaboration_id)
            .with_for_update()
        ).scalar_one_or_none()

        if offer is None or offer.role != CollaborationRole.OWNER or offer.status != CollaborationStatus.PENDING:
            raise OwnershipOfferNotFoundError(collaboration_id=collaboration_id)

        # Bind offer to the URL app_id when provided — prevents cross-app path confusion.
        if app_id is not None and int(offer.app_id) != int(app_id):
            raise OwnershipOfferNotFoundError(collaboration_id=collaboration_id)

        if int(offer.user_id) != int(actor_user_id):
            raise NotOfferRecipientError(actor_user_id, collaboration_id)

        app_id = offer.app_id
        recipient_id: int = int(offer.user_id)

        app: App | None = db.execute(
            select(App).where(App.app_id == app_id).with_for_update()
        ).scalar_one_or_none()

        if app is None:
            raise AppNotFoundError(app_id)

        previous_owner_id: int = app.owner_id

        try:
            # _reassign_owner's collaborator-hygiene step will find and db.delete()
            # the offer row (user_id=recipient_id on this app). Do NOT call
            # db.delete(offer) again — it is already pending-delete after this call.
            AppOwnershipService._reassign_owner(
                db, app, recipient_id, actor_user_id=actor_user_id
            )

            # Demote previous owner to ADMINISTRATOR so they retain access (FR-D3).
            collab_repo = AppCollaborationRepository(db)
            prev_owner_collab: AppCollaborator | None = (
                collab_repo.get_collaboration_by_app_and_user(app_id, previous_owner_id)
            )

            if prev_owner_collab is not None:
                prev_owner_collab.role = CollaborationRole.ADMINISTRATOR
                prev_owner_collab.status = CollaborationStatus.ACCEPTED
                prev_owner_collab.accepted_at = datetime.now()
                db.add(prev_owner_collab)
                logger.info(
                    f"accept: updated previous owner row collab_id={prev_owner_collab.id} "
                    f"to ADMINISTRATOR/ACCEPTED app_id={app_id} user_id={previous_owner_id}"
                )
            else:
                demoted_collab = AppCollaborator(
                    app_id=app_id,
                    user_id=previous_owner_id,
                    role=CollaborationRole.ADMINISTRATOR,
                    status=CollaborationStatus.ACCEPTED,
                    invited_by=actor_user_id,
                    invited_at=datetime.now(),
                    accepted_at=datetime.now(),
                )
                db.add(demoted_collab)
                logger.info(
                    f"accept: created ADMINISTRATOR row for previous owner user_id={previous_owner_id} "
                    f"app_id={app_id} actor_user_id={actor_user_id}"
                )

            db.commit()
            db.refresh(app)
        except Exception:
            db.rollback()
            logger.error(
                f"accept: rollback collaboration_id={collaboration_id} "
                f"actor_user_id={actor_user_id}",
                exc_info=True,
            )
            raise

        logger.info(
            f"accept: complete app_id={app_id} previous_owner_id={previous_owner_id} "
            f"new_owner_id={recipient_id} actor_user_id={actor_user_id}"
        )

        return app, previous_owner_id

    @staticmethod
    def decline(
        db: Session,
        collaboration_id: int,
        *,
        actor_user_id: int,
        app_id: int | None = None,
    ) -> None:
        """Decline a pending ownership offer (recipient only). Sets status to DECLINED.

        Raises:
            OwnershipOfferNotFoundError: Offer not found or not PENDING OWNER (→ 404).
            NotOfferRecipientError: Actor is not the named recipient (→ 403).
        """
        logger.info(
            f"decline: start collaboration_id={collaboration_id} actor_user_id={actor_user_id}"
        )

        offer: AppCollaborator | None = db.execute(
            select(AppCollaborator)
            .where(AppCollaborator.id == collaboration_id)
            .with_for_update()
        ).scalar_one_or_none()

        if offer is None or offer.role != CollaborationRole.OWNER or offer.status != CollaborationStatus.PENDING:
            raise OwnershipOfferNotFoundError(collaboration_id=collaboration_id)

        if app_id is not None and int(offer.app_id) != int(app_id):
            raise OwnershipOfferNotFoundError(collaboration_id=collaboration_id)

        if int(offer.user_id) != int(actor_user_id):
            raise NotOfferRecipientError(actor_user_id, collaboration_id)

        try:
            offer.status = CollaborationStatus.DECLINED
            db.add(offer)
            db.commit()
        except Exception:
            db.rollback()
            logger.error(
                f"decline: rollback collaboration_id={collaboration_id} "
                f"actor_user_id={actor_user_id}",
                exc_info=True,
            )
            raise

        logger.info(
            f"decline: complete collaboration_id={collaboration_id} "
            f"app_id={offer.app_id} actor_user_id={actor_user_id}"
        )

    @staticmethod
    def cancel(
        db: Session,
        app_id: int,
        *,
        actor_user_id: int,
    ) -> None:
        """Cancel the pending ownership offer for an app (owner/omniadmin only).

        Deletes all PENDING OWNER rows for the app. Deleting every match is robust
        against legacy multi-offer rows and avoids MultipleResultsFound.

        Raises:
            OwnershipOfferNotFoundError: No PENDING OWNER offer exists for this app (→ 404).
        """
        logger.info(
            f"cancel: start app_id={app_id} actor_user_id={actor_user_id}"
        )

        offers = db.execute(
            select(AppCollaborator)
            .where(
                AppCollaborator.app_id == app_id,
                AppCollaborator.role == CollaborationRole.OWNER,
                AppCollaborator.status == CollaborationStatus.PENDING,
            )
            .with_for_update()
        ).scalars().all()

        if not offers:
            raise OwnershipOfferNotFoundError(app_id=app_id)

        try:
            for off in offers:
                db.delete(off)
            db.commit()
        except Exception:
            db.rollback()
            logger.error(
                f"cancel: rollback app_id={app_id} actor_user_id={actor_user_id}",
                exc_info=True,
            )
            raise

        logger.info(
            f"cancel: complete app_id={app_id} cancelled_count={len(offers)} "
            f"actor_user_id={actor_user_id}"
        )
