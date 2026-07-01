"""Integration tests for AppOwnershipService voluntary transfer (step_005).

Maps to spec FR-D / AC-10 / FR-G4 / AD-5.

Tests:
  1.  offer creates a PENDING OWNER AppCollaborator row; no App.owner_id change;
      surfaces in get_user_pending_invitations.
  2.  offer is idempotent — second call to the same recipient refreshes, no duplicate.
  3.  offer with invalid recipient (nonexistent / inactive / current-owner) raises
      TransferRecipientInvalidError; missing app raises AppNotFoundError.
  4.  accept happy path: App.owner_id becomes recipient; previous owner has an
      ADMINISTRATOR/ACCEPTED collaborator row; pending OWNER offer row is gone;
      returns (app, previous_owner_id) correctly.
  5.  accept by a non-recipient (actor != offer.user_id) raises NotOfferRecipientError
      and makes no change (owner unchanged).
  6.  accept of a nonexistent offer / already-declined offer raises
      OwnershipOfferNotFoundError; no mutation.
  7.  decline by recipient sets status=DECLINED, does not change owner;
      cancel by owner deletes the pending row (no owner change).
  8.  SaaS tier check on accept is a no-op in self-managed test config (documented
      note; the code path is covered by the transfer_direct test suite).
  9.  AD-5 safety: while an offer is PENDING the recipient is NOT the owner —
      App.owner_id still resolves to the original owner.

Transaction isolation: every test runs inside the conftest savepoint-based
rollback; nothing persists between tests.

Run with:
    pytest tests/integration/test_app_ownership_voluntary.py -v
"""

import pytest
from sqlalchemy import select

from tests.factories import (
    UserFactory,
    AppFactory,
    configure_factories,
)


# ===========================================================================
# Test 1 — offer creates PENDING OWNER row; App.owner_id unchanged;
#           row surfaces in get_user_pending_invitations
# ===========================================================================


class TestOfferCreatesRow:

    def test_offer_creates_pending_owner_collaborator_row(self, db):
        """AC-10 / FR-D2: offer() creates AppCollaborator(role=OWNER, status=PENDING).

        No change to App.owner_id before accept.
        """
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app = AppFactory(owner=owner)
        app_id = app.app_id
        original_owner_id = owner.user_id
        recipient_id = recipient.user_id

        from services.app_ownership_service import AppOwnershipService
        from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
        from models.app import App

        offer_row = AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient_id, actor_user_id=owner.user_id
        )

        # The returned row must be the offer row.
        assert offer_row is not None
        assert offer_row.app_id == app_id
        assert offer_row.user_id == recipient_id
        assert offer_row.role == CollaborationRole.OWNER
        assert offer_row.status == CollaborationStatus.PENDING
        assert offer_row.invited_by == owner.user_id

        # App.owner_id must NOT have changed.
        db.expire_all()
        refreshed_app = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed_app.owner_id == original_owner_id

        # Confirm the row exists in the DB via a direct query.
        row = db.execute(
            select(AppCollaborator).where(
                AppCollaborator.id == offer_row.id
            )
        ).scalar_one_or_none()
        assert row is not None
        assert row.role == CollaborationRole.OWNER
        assert row.status == CollaborationStatus.PENDING

    def test_offer_surfaces_in_pending_invitations(self, db):
        """FR-D1: the PENDING OWNER offer appears in get_user_pending_invitations for recipient."""
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app = AppFactory(owner=owner)
        recipient_id = recipient.user_id

        from services.app_ownership_service import AppOwnershipService
        from repositories.app_collaboration_repository import AppCollaborationRepository
        from models.app_collaborator import CollaborationRole, CollaborationStatus

        offer_row = AppOwnershipService.offer(
            db, app_id=app.app_id, new_owner_id=recipient_id, actor_user_id=owner.user_id
        )

        repo = AppCollaborationRepository(db)
        pending = repo.get_user_pending_invitations(recipient_id)

        pending_ids = [p.id for p in pending]
        assert offer_row.id in pending_ids

        # All returned rows must be PENDING for this user.
        for p in pending:
            assert p.user_id == recipient_id
            assert p.status == CollaborationStatus.PENDING

        # At least one must be the OWNER role (our offer).
        owner_pending = [p for p in pending if p.role == CollaborationRole.OWNER]
        assert len(owner_pending) >= 1


# ===========================================================================
# Test 2 — offer idempotency
# ===========================================================================


class TestOfferIdempotency:

    def test_second_offer_to_same_recipient_does_not_create_duplicate(self, db):
        """FR-D2: a second offer() to the same recipient refreshes the existing row, no new row."""
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app = AppFactory(owner=owner)
        app_id = app.app_id
        recipient_id = recipient.user_id

        from services.app_ownership_service import AppOwnershipService
        from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus

        first_offer = AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient_id, actor_user_id=owner.user_id
        )
        first_id = first_offer.id

        # Second offer — same app, same recipient.
        second_offer = AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient_id, actor_user_id=owner.user_id
        )

        # No duplicate row: both calls reference the same PK.
        assert second_offer.id == first_id

        # Exactly one PENDING OWNER row exists for this (app, recipient) pair.
        all_rows = db.execute(
            select(AppCollaborator).where(
                AppCollaborator.app_id == app_id,
                AppCollaborator.user_id == recipient_id,
                AppCollaborator.role == CollaborationRole.OWNER,
                AppCollaborator.status == CollaborationStatus.PENDING,
            )
        ).scalars().all()
        assert len(all_rows) == 1


# ===========================================================================
# Test 3 — offer input validation
# ===========================================================================


class TestOfferValidation:

    def test_offer_to_nonexistent_user_raises_transfer_recipient_invalid_error(self, db):
        """FR-D2 / FR-C2: nonexistent recipient raises TransferRecipientInvalidError."""
        configure_factories(db)
        owner = UserFactory()
        app = AppFactory(owner=owner)

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import TransferRecipientInvalidError

        with pytest.raises(TransferRecipientInvalidError):
            AppOwnershipService.offer(
                db, app_id=app.app_id, new_owner_id=999999, actor_user_id=owner.user_id
            )

    def test_offer_to_inactive_user_raises_transfer_recipient_invalid_error(self, db):
        """FR-C2: inactive recipient raises TransferRecipientInvalidError."""
        configure_factories(db)
        owner = UserFactory()
        app = AppFactory(owner=owner)
        inactive_recipient = UserFactory(is_active=False)

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import TransferRecipientInvalidError

        with pytest.raises(TransferRecipientInvalidError):
            AppOwnershipService.offer(
                db,
                app_id=app.app_id,
                new_owner_id=inactive_recipient.user_id,
                actor_user_id=owner.user_id,
            )

    def test_offer_to_current_owner_raises_transfer_recipient_invalid_error(self, db):
        """FR-C2: offering to the current owner raises TransferRecipientInvalidError."""
        configure_factories(db)
        owner = UserFactory()
        app = AppFactory(owner=owner)

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import TransferRecipientInvalidError

        with pytest.raises(TransferRecipientInvalidError):
            AppOwnershipService.offer(
                db,
                app_id=app.app_id,
                new_owner_id=owner.user_id,
                actor_user_id=owner.user_id,
            )

    def test_offer_on_missing_app_raises_app_not_found_error(self, db):
        """FR-D2: nonexistent app_id raises AppNotFoundError."""
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import AppNotFoundError

        with pytest.raises(AppNotFoundError):
            AppOwnershipService.offer(
                db, app_id=999999, new_owner_id=recipient.user_id, actor_user_id=owner.user_id
            )

    def test_invalid_offer_makes_no_change_to_app(self, db):
        """Validation errors leave App.owner_id unchanged."""
        configure_factories(db)
        owner = UserFactory()
        app = AppFactory(owner=owner)
        original_owner_id = owner.user_id
        app_id = app.app_id

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import TransferRecipientInvalidError
        from models.app import App

        with pytest.raises(TransferRecipientInvalidError):
            AppOwnershipService.offer(
                db, app_id=app_id, new_owner_id=999999, actor_user_id=owner.user_id
            )

        db.expire_all()
        refreshed = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed.owner_id == original_owner_id


# ===========================================================================
# Test 4 — accept happy path
# ===========================================================================


class TestAcceptHappyPath:

    def test_accept_reassigns_owner_and_demotes_previous_owner(self, db):
        """AC-10 / FR-D3: accept() reassigns App.owner_id, demotes old owner to
        ADMINISTRATOR/ACCEPTED collaborator, clears the PENDING OWNER offer row.

        The service commits inside offer() and accept(), which under the savepoint
        isolation pattern emits SAVEPOINT / RELEASE SAVEPOINT.  We commit the setup
        first so that the service's own rollback on error does not wipe fixture rows.
        """
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app = AppFactory(owner=owner)
        app_id = app.app_id
        owner_id = owner.user_id
        recipient_id = recipient.user_id

        # Commit setup through the savepoint so the service's atomic commit does not
        # roll back to before the fixtures were visible.
        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from models.app import App
        from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus

        offer_row = AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient_id, actor_user_id=owner_id
        )
        offer_id = offer_row.id

        result_app, prev_owner_id = AppOwnershipService.accept(
            db, collaboration_id=offer_id, actor_user_id=recipient_id
        )

        # Return values must match.
        assert prev_owner_id == owner_id
        assert result_app.owner_id == recipient_id

        db.expire_all()

        # App.owner_id in DB must be recipient.
        refreshed_app = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed_app.owner_id == recipient_id

        # The PENDING OWNER offer row must be gone.
        offer_after = db.execute(
            select(AppCollaborator).where(AppCollaborator.id == offer_id)
        ).scalar_one_or_none()
        assert offer_after is None, "PENDING OWNER offer row must be removed after accept"

        # The previous owner must now have an ADMINISTRATOR/ACCEPTED collaborator row.
        prev_owner_collab = db.execute(
            select(AppCollaborator).where(
                AppCollaborator.app_id == app_id,
                AppCollaborator.user_id == owner_id,
            )
        ).scalar_one_or_none()
        assert prev_owner_collab is not None, (
            "Previous owner must have a collaborator row after accept (FR-D3)"
        )
        assert prev_owner_collab.role == CollaborationRole.ADMINISTRATOR
        assert prev_owner_collab.status == CollaborationStatus.ACCEPTED

    def test_accept_returns_correct_previous_owner_id(self, db):
        """FR-D3: the returned previous_owner_id equals the app's original owner."""
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app = AppFactory(owner=owner)
        expected_prev_owner_id = owner.user_id
        db.commit()

        from services.app_ownership_service import AppOwnershipService

        offer_row = AppOwnershipService.offer(
            db, app_id=app.app_id, new_owner_id=recipient.user_id, actor_user_id=owner.user_id
        )
        _, prev_owner_id = AppOwnershipService.accept(
            db, collaboration_id=offer_row.id, actor_user_id=recipient.user_id
        )
        assert prev_owner_id == expected_prev_owner_id

    def test_accept_when_previous_owner_already_has_collaborator_row_updates_it(self, db):
        """FR-D3: if the previous owner already had a collaborator row, it is updated to
        ADMINISTRATOR/ACCEPTED rather than a duplicate being created.
        """
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app = AppFactory(owner=owner)
        app_id = app.app_id
        owner_id = owner.user_id
        db.commit()

        from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
        from services.app_ownership_service import AppOwnershipService
        from datetime import datetime

        # Pre-create an EDITOR collaborator row for the owner (unusual but possible).
        existing_collab = AppCollaborator(
            app_id=app_id,
            user_id=owner_id,
            role=CollaborationRole.EDITOR,
            status=CollaborationStatus.ACCEPTED,
            invited_by=owner_id,
            invited_at=datetime.now(),
            accepted_at=datetime.now(),
        )
        db.add(existing_collab)
        db.commit()
        existing_collab_id = existing_collab.id

        offer_row = AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient.user_id, actor_user_id=owner_id
        )
        AppOwnershipService.accept(
            db, collaboration_id=offer_row.id, actor_user_id=recipient.user_id
        )

        db.expire_all()

        # Only one collaborator row for the previous owner (updated, not duplicated).
        owner_collabs = db.execute(
            select(AppCollaborator).where(
                AppCollaborator.app_id == app_id,
                AppCollaborator.user_id == owner_id,
            )
        ).scalars().all()
        assert len(owner_collabs) == 1
        assert owner_collabs[0].role == CollaborationRole.ADMINISTRATOR
        assert owner_collabs[0].status == CollaborationStatus.ACCEPTED


# ===========================================================================
# Test 5 — accept by a non-recipient raises NotOfferRecipientError; no change
# ===========================================================================


class TestAcceptByNonRecipient:

    def test_accept_by_wrong_user_raises_not_offer_recipient_error(self, db):
        """AC-10 / FR-D3: only the named recipient may accept; others get NotOfferRecipientError (403)."""
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        interloper = UserFactory()
        app = AppFactory(owner=owner)
        app_id = app.app_id
        original_owner_id = owner.user_id
        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import NotOfferRecipientError
        from models.app import App

        offer_row = AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient.user_id, actor_user_id=owner.user_id
        )
        offer_id = offer_row.id

        with pytest.raises(NotOfferRecipientError) as exc_info:
            AppOwnershipService.accept(
                db, collaboration_id=offer_id, actor_user_id=interloper.user_id
            )

        err = exc_info.value
        assert err.actor_user_id == interloper.user_id
        assert err.collaboration_id == offer_id

        # No ownership change.
        db.expire_all()
        refreshed = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed.owner_id == original_owner_id

    def test_accept_by_wrong_user_leaves_offer_row_intact(self, db):
        """Rejecting a non-recipient accept must not modify the PENDING offer row."""
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        interloper = UserFactory()
        app = AppFactory(owner=owner)
        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import NotOfferRecipientError
        from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus

        offer_row = AppOwnershipService.offer(
            db, app_id=app.app_id, new_owner_id=recipient.user_id, actor_user_id=owner.user_id
        )
        offer_id = offer_row.id

        with pytest.raises(NotOfferRecipientError):
            AppOwnershipService.accept(
                db, collaboration_id=offer_id, actor_user_id=interloper.user_id
            )

        db.expire_all()
        # Offer row still exists and is still PENDING.
        surviving = db.execute(
            select(AppCollaborator).where(AppCollaborator.id == offer_id)
        ).scalar_one_or_none()
        assert surviving is not None
        assert surviving.role == CollaborationRole.OWNER
        assert surviving.status == CollaborationStatus.PENDING


# ===========================================================================
# Test 6 — accept of nonexistent / declined offer raises OwnershipOfferNotFoundError
# ===========================================================================


class TestAcceptNonexistentOrDeclinedOffer:

    def test_accept_nonexistent_collaboration_id_raises_ownership_offer_not_found_error(self, db):
        """FR-D3: accept() on a nonexistent collaboration_id raises OwnershipOfferNotFoundError (404)."""
        configure_factories(db)
        actor = UserFactory()

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import OwnershipOfferNotFoundError

        with pytest.raises(OwnershipOfferNotFoundError):
            AppOwnershipService.accept(
                db, collaboration_id=999999, actor_user_id=actor.user_id
            )

    def test_accept_already_declined_offer_raises_ownership_offer_not_found_error(self, db):
        """FR-D3: accept() on a DECLINED row raises OwnershipOfferNotFoundError (not 200)."""
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app = AppFactory(owner=owner)
        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import OwnershipOfferNotFoundError

        offer_row = AppOwnershipService.offer(
            db, app_id=app.app_id, new_owner_id=recipient.user_id, actor_user_id=owner.user_id
        )
        offer_id = offer_row.id

        # Recipient declines.
        AppOwnershipService.decline(
            db, collaboration_id=offer_id, actor_user_id=recipient.user_id
        )

        # Trying to accept a DECLINED offer must raise.
        with pytest.raises(OwnershipOfferNotFoundError):
            AppOwnershipService.accept(
                db, collaboration_id=offer_id, actor_user_id=recipient.user_id
            )

    def test_accept_nonexistent_offer_makes_no_mutation(self, db):
        """No side effect when accept() raises for a nonexistent offer."""
        configure_factories(db)
        owner = UserFactory()
        app = AppFactory(owner=owner)
        original_owner_id = owner.user_id
        app_id = app.app_id

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import OwnershipOfferNotFoundError
        from models.app import App

        with pytest.raises(OwnershipOfferNotFoundError):
            AppOwnershipService.accept(
                db, collaboration_id=999999, actor_user_id=owner.user_id
            )

        db.expire_all()
        refreshed = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed.owner_id == original_owner_id


# ===========================================================================
# Test 7 — decline and cancel
# ===========================================================================


class TestDeclineAndCancel:

    def test_decline_sets_status_declined_and_does_not_change_owner(self, db):
        """FR-D4: recipient decline sets offer status=DECLINED; App.owner_id unchanged."""
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app = AppFactory(owner=owner)
        original_owner_id = owner.user_id
        app_id = app.app_id
        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from models.app import App
        from models.app_collaborator import AppCollaborator, CollaborationStatus

        offer_row = AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient.user_id, actor_user_id=owner.user_id
        )
        offer_id = offer_row.id

        AppOwnershipService.decline(
            db, collaboration_id=offer_id, actor_user_id=recipient.user_id
        )

        db.expire_all()

        # App.owner_id unchanged.
        refreshed_app = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed_app.owner_id == original_owner_id

        # Offer row status is DECLINED (not removed).
        offer_after = db.execute(
            select(AppCollaborator).where(AppCollaborator.id == offer_id)
        ).scalar_one_or_none()
        assert offer_after is not None
        assert offer_after.status == CollaborationStatus.DECLINED

    def test_decline_by_non_recipient_raises_not_offer_recipient_error(self, db):
        """FR-D4: a user other than the recipient cannot decline."""
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        interloper = UserFactory()
        app = AppFactory(owner=owner)
        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import NotOfferRecipientError

        offer_row = AppOwnershipService.offer(
            db, app_id=app.app_id, new_owner_id=recipient.user_id, actor_user_id=owner.user_id
        )

        with pytest.raises(NotOfferRecipientError):
            AppOwnershipService.decline(
                db, collaboration_id=offer_row.id, actor_user_id=interloper.user_id
            )

    def test_cancel_removes_pending_offer_row_and_does_not_change_owner(self, db):
        """FR-D4: owner cancel deletes the PENDING OWNER row; App.owner_id unchanged."""
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app = AppFactory(owner=owner)
        original_owner_id = owner.user_id
        app_id = app.app_id
        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from models.app import App
        from models.app_collaborator import AppCollaborator

        offer_row = AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient.user_id, actor_user_id=owner.user_id
        )
        offer_id = offer_row.id

        AppOwnershipService.cancel(db, app_id=app_id, actor_user_id=owner.user_id)

        db.expire_all()

        # App.owner_id unchanged.
        refreshed_app = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed_app.owner_id == original_owner_id

        # Offer row must be gone (deleted, not just DECLINED).
        offer_after = db.execute(
            select(AppCollaborator).where(AppCollaborator.id == offer_id)
        ).scalar_one_or_none()
        assert offer_after is None, "cancel() must delete the offer row (not just flip status)"

    def test_cancel_on_app_with_no_pending_offer_raises_ownership_offer_not_found_error(self, db):
        """cancel() when no PENDING offer exists raises OwnershipOfferNotFoundError."""
        configure_factories(db)
        owner = UserFactory()
        app = AppFactory(owner=owner)

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import OwnershipOfferNotFoundError

        with pytest.raises(OwnershipOfferNotFoundError):
            AppOwnershipService.cancel(
                db, app_id=app.app_id, actor_user_id=owner.user_id
            )


# ===========================================================================
# Test 8 — SaaS tier check is no-op in self-managed config (note test)
# ===========================================================================


class TestTierEnforcementNoOpSelfManaged:

    def test_accept_does_not_raise_tier_limit_in_self_managed_mode(self, db):
        """FR-C4 / SaaS: TierEnforcementService.check_app_limit is a no-op in
        self-managed mode (AICT_DEPLOYMENT_MODE not set to 'saas' in test config).

        This test verifies that accept() completes successfully even when the
        recipient already owns multiple apps — proving tier enforcement is off.
        The SaaS tier-limit path (TierLimitExceededError) is exercised in the
        transfer_direct tests which share the same _reassign_owner primitive.
        """
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        # Give recipient several existing apps (exceeds any reasonable free-tier limit).
        for _ in range(5):
            AppFactory(owner=recipient)
        app = AppFactory(owner=owner)
        db.commit()

        from services.app_ownership_service import AppOwnershipService

        offer_row = AppOwnershipService.offer(
            db, app_id=app.app_id, new_owner_id=recipient.user_id, actor_user_id=owner.user_id
        )
        # Must not raise TierLimitExceededError in self-managed mode.
        result_app, _ = AppOwnershipService.accept(
            db, collaboration_id=offer_row.id, actor_user_id=recipient.user_id
        )
        assert result_app.owner_id == recipient.user_id


# ===========================================================================
# Test 9 — AD-5 safety: PENDING OWNER offer grants NO access (owner_id unchanged)
# ===========================================================================


class TestPendingOfferGrantsNoAccess:

    def test_pending_offer_does_not_change_owner_id(self, db):
        """AD-5: a PENDING OWNER AppCollaborator row does NOT change App.owner_id.

        Role resolution (resolve_user_app_role / get_user_app_role) derives OWNER
        solely from App.owner_id, so a pending offer grants nothing until accept.
        """
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app = AppFactory(owner=owner)
        app_id = app.app_id
        original_owner_id = owner.user_id
        recipient_id = recipient.user_id

        from services.app_ownership_service import AppOwnershipService
        from repositories.app_collaboration_repository import AppCollaborationRepository
        from models.app import App

        AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient_id, actor_user_id=owner.user_id
        )

        # App.owner_id must still be the original owner.
        db.expire_all()
        refreshed = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed.owner_id == original_owner_id, (
            "AD-5: PENDING OWNER offer must not change App.owner_id"
        )

        # The role query must return OWNER for the original owner, not the recipient.
        repo = AppCollaborationRepository(db)
        original_owner_role = repo.get_user_app_role(original_owner_id, app_id)
        assert original_owner_role == "owner", (
            "Original owner must still resolve as 'owner' while offer is PENDING"
        )

        # The recipient's role must NOT be 'owner' (the PENDING row grants nothing).
        recipient_role = repo.get_user_app_role(recipient_id, app_id)
        assert recipient_role != "owner", (
            "AD-5: recipient must not resolve as 'owner' while offer is only PENDING"
        )

    def test_original_owner_role_resolves_correctly_throughout_offer_lifecycle(self, db):
        """Comprehensive AD-5: original owner is 'owner' at offer time, PENDING time,
        and 'administrator' (via collaborator row) after accept completes.
        """
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app = AppFactory(owner=owner)
        app_id = app.app_id
        owner_id = owner.user_id
        recipient_id = recipient.user_id
        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from repositories.app_collaboration_repository import AppCollaborationRepository
        from models.app import App

        repo = AppCollaborationRepository(db)

        # Phase 1: before any offer — original owner resolves as 'owner'.
        assert repo.get_user_app_role(owner_id, app_id) == "owner"
        assert repo.get_user_app_role(recipient_id, app_id) is None

        # Phase 2: offer created — original owner still 'owner', recipient is NOT 'owner'.
        offer_row = AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient_id, actor_user_id=owner_id
        )
        db.expire_all()
        assert repo.get_user_app_role(owner_id, app_id) == "owner"
        assert repo.get_user_app_role(recipient_id, app_id) != "owner"

        # Phase 3: accept — recipient is now owner; previous owner is ADMINISTRATOR.
        AppOwnershipService.accept(
            db, collaboration_id=offer_row.id, actor_user_id=recipient_id
        )
        db.expire_all()

        refreshed = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed.owner_id == recipient_id

        # Previous owner no longer resolves as 'owner' via App.owner_id.
        prev_owner_role = repo.get_user_app_role(owner_id, app_id)
        # After accept, the previous owner has an ADMINISTRATOR collaborator row, so
        # get_user_app_role returns 'administrator' (not 'owner').
        assert prev_owner_role == "administrator", (
            f"Previous owner should have 'administrator' role after accept; got {prev_owner_role!r}"
        )

        new_owner_role = repo.get_user_app_role(recipient_id, app_id)
        assert new_owner_role == "owner", (
            f"New owner should resolve as 'owner' via App.owner_id; got {new_owner_role!r}"
        )


# ===========================================================================
# Fix A — single active pending OWNER offer per app (supersede logic)
# ===========================================================================


class TestOfferSupersede:
    """Fix A: offer() supersedes any existing pending OWNER offer to a *different*
    recipient so there is at most ONE pending OWNER AppCollaborator row per app.
    cancel() deletes ALL matching rows (was scalar_one_or_none → MultipleResultsFound).
    """

    def test_second_offer_to_different_recipient_supersedes_first(self, db):
        """Offer to B on app X while A's offer is still PENDING:
        - A's offer row is deleted (superseded).
        - Exactly one PENDING OWNER row remains; it belongs to B.
        - App.owner_id is unchanged throughout.
        """
        configure_factories(db)
        owner = UserFactory()
        recipient_a = UserFactory()
        recipient_b = UserFactory()
        app = AppFactory(owner=owner)
        app_id = app.app_id
        original_owner_id = owner.user_id

        db.commit()  # flush fixtures through the savepoint so service commits don't wipe them

        from services.app_ownership_service import AppOwnershipService
        from models.app import App
        from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus

        # First offer: to recipient A.
        offer_a = AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient_a.user_id, actor_user_id=owner.user_id
        )
        offer_a_id = offer_a.id

        # Second offer on the SAME app to a DIFFERENT recipient B.
        offer_b = AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient_b.user_id, actor_user_id=owner.user_id
        )

        db.expire_all()

        # A's offer row must be gone (superseded / deleted).
        offer_a_after = db.execute(
            select(AppCollaborator).where(AppCollaborator.id == offer_a_id)
        ).scalar_one_or_none()
        assert offer_a_after is None, (
            "Fix A: offer to A must be superseded/deleted when a new offer is made to B"
        )

        # Exactly one PENDING OWNER row for this app.
        pending_owner_rows = db.execute(
            select(AppCollaborator).where(
                AppCollaborator.app_id == app_id,
                AppCollaborator.role == CollaborationRole.OWNER,
                AppCollaborator.status == CollaborationStatus.PENDING,
            )
        ).scalars().all()
        assert len(pending_owner_rows) == 1, (
            f"Fix A: expected exactly 1 PENDING OWNER row after supersede, "
            f"got {len(pending_owner_rows)}"
        )
        assert pending_owner_rows[0].user_id == recipient_b.user_id, (
            "Fix A: the surviving PENDING OWNER row must belong to B"
        )

        # App.owner_id must still be the original owner.
        refreshed_app = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed_app.owner_id == original_owner_id, (
            "App.owner_id must remain the original owner after a supersede offer"
        )

    def test_cancel_after_supersede_removes_remaining_offer_without_error(self, db):
        """After a supersede (offer A → offer B), cancel(app_id) succeeds:
        - Deletes B's remaining pending OWNER row.
        - Raises no exception (in particular no MultipleResultsFound).
        - App.owner_id unchanged.
        """
        configure_factories(db)
        owner = UserFactory()
        recipient_a = UserFactory()
        recipient_b = UserFactory()
        app = AppFactory(owner=owner)
        app_id = app.app_id
        original_owner_id = owner.user_id

        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from models.app import App
        from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus

        # Supersede: offer to A then to B.
        AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient_a.user_id, actor_user_id=owner.user_id
        )
        offer_b = AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient_b.user_id, actor_user_id=owner.user_id
        )
        offer_b_id = offer_b.id

        # cancel must not raise MultipleResultsFound (was the bug) or any other exception.
        AppOwnershipService.cancel(db, app_id=app_id, actor_user_id=owner.user_id)

        db.expire_all()

        # B's offer row must be gone.
        offer_b_after = db.execute(
            select(AppCollaborator).where(AppCollaborator.id == offer_b_id)
        ).scalar_one_or_none()
        assert offer_b_after is None, (
            "cancel() must delete B's remaining PENDING OWNER row after supersede"
        )

        # No PENDING OWNER rows left.
        remaining = db.execute(
            select(AppCollaborator).where(
                AppCollaborator.app_id == app_id,
                AppCollaborator.role == CollaborationRole.OWNER,
                AppCollaborator.status == CollaborationStatus.PENDING,
            )
        ).scalars().all()
        assert remaining == [], "No PENDING OWNER rows should remain after cancel()"

        # App.owner_id unchanged.
        refreshed_app = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed_app.owner_id == original_owner_id

    def test_cancel_deletes_all_pending_owner_rows_even_when_multiple_exist(self, db):
        """Robustness: if two PENDING OWNER rows exist for the same app (e.g. legacy
        data that bypassed offer()), cancel() deletes BOTH and raises nothing.

        We insert the second row directly via AppCollaboratorFactory, bypassing the
        offer() supersede guard, to simulate legacy/inconsistent DB state.
        """
        configure_factories(db)
        owner = UserFactory()
        recipient_a = UserFactory()
        recipient_b = UserFactory()
        app = AppFactory(owner=owner)
        app_id = app.app_id
        original_owner_id = owner.user_id

        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from models.app import App
        from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
        from datetime import datetime

        # Insert two PENDING OWNER rows directly (bypassing offer() supersede logic).
        row_a = AppCollaborator(
            app_id=app_id,
            user_id=recipient_a.user_id,
            role=CollaborationRole.OWNER,
            status=CollaborationStatus.PENDING,
            invited_by=owner.user_id,
            invited_at=datetime.now(),
        )
        row_b = AppCollaborator(
            app_id=app_id,
            user_id=recipient_b.user_id,
            role=CollaborationRole.OWNER,
            status=CollaborationStatus.PENDING,
            invited_by=owner.user_id,
            invited_at=datetime.now(),
        )
        db.add(row_a)
        db.add(row_b)
        db.commit()

        row_a_id = row_a.id
        row_b_id = row_b.id

        # cancel() must delete BOTH rows without raising MultipleResultsFound or any other error.
        AppOwnershipService.cancel(db, app_id=app_id, actor_user_id=owner.user_id)

        db.expire_all()

        assert db.execute(
            select(AppCollaborator).where(AppCollaborator.id == row_a_id)
        ).scalar_one_or_none() is None, "Row A must be deleted by cancel()"

        assert db.execute(
            select(AppCollaborator).where(AppCollaborator.id == row_b_id)
        ).scalar_one_or_none() is None, "Row B must be deleted by cancel()"

        # App.owner_id unchanged.
        refreshed_app = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed_app.owner_id == original_owner_id


# ===========================================================================
# Fix B — cross-app binding on accept/decline
# ===========================================================================


class TestCrossAppBinding:
    """Fix B: accept() and decline() now accept an optional app_id parameter.
    When app_id is provided and the offer's app_id does not match, both methods
    raise OwnershipOfferNotFoundError — preventing cross-app path confusion.
    """

    def test_accept_with_wrong_app_id_raises_ownership_offer_not_found_error(self, db):
        """Create offer on app X; call accept(..., app_id=<app Y>) → OwnershipOfferNotFoundError.
        App X's owner_id must be unchanged.
        """
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app_x = AppFactory(owner=owner)
        app_y = AppFactory(owner=owner)
        app_x_id = app_x.app_id
        app_y_id = app_y.app_id
        original_owner_id = owner.user_id

        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import OwnershipOfferNotFoundError
        from models.app import App

        offer = AppOwnershipService.offer(
            db, app_id=app_x_id, new_owner_id=recipient.user_id, actor_user_id=owner.user_id
        )
        offer_id = offer.id

        # Accept the offer but supply the WRONG app_id (app Y instead of app X).
        with pytest.raises(OwnershipOfferNotFoundError):
            AppOwnershipService.accept(
                db,
                collaboration_id=offer_id,
                actor_user_id=recipient.user_id,
                app_id=app_y_id,  # wrong app
            )

        db.expire_all()

        # App X's owner must still be the original owner.
        refreshed_x = db.execute(select(App).where(App.app_id == app_x_id)).scalar_one()
        assert refreshed_x.owner_id == original_owner_id, (
            "Fix B: cross-app accept must not reassign ownership on app X"
        )

        # App Y's owner must also remain the original owner (no side effect).
        refreshed_y = db.execute(select(App).where(App.app_id == app_y_id)).scalar_one()
        assert refreshed_y.owner_id == original_owner_id, (
            "Fix B: cross-app accept must not reassign ownership on app Y either"
        )

    def test_decline_with_wrong_app_id_raises_ownership_offer_not_found_and_offer_stays_pending(self, db):
        """Create offer on app X; call decline(..., app_id=<app Y>) → OwnershipOfferNotFoundError.
        The offer must still exist and be PENDING after the failed decline.
        """
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app_x = AppFactory(owner=owner)
        app_y = AppFactory(owner=owner)
        app_x_id = app_x.app_id
        app_y_id = app_y.app_id

        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import OwnershipOfferNotFoundError
        from models.app_collaborator import AppCollaborator, CollaborationStatus

        offer = AppOwnershipService.offer(
            db, app_id=app_x_id, new_owner_id=recipient.user_id, actor_user_id=owner.user_id
        )
        offer_id = offer.id

        # Decline with the WRONG app_id.
        with pytest.raises(OwnershipOfferNotFoundError):
            AppOwnershipService.decline(
                db,
                collaboration_id=offer_id,
                actor_user_id=recipient.user_id,
                app_id=app_y_id,  # wrong app
            )

        db.expire_all()

        # Offer must still exist and be PENDING.
        surviving = db.execute(
            select(AppCollaborator).where(AppCollaborator.id == offer_id)
        ).scalar_one_or_none()
        assert surviving is not None, (
            "Fix B: offer row must not be modified when decline() is called with wrong app_id"
        )
        assert surviving.status == CollaborationStatus.PENDING, (
            "Fix B: offer status must remain PENDING after a failed cross-app decline"
        )

    def test_accept_with_correct_app_id_still_works(self, db):
        """Sanity: accept(..., app_id=<correct app X id>) succeeds and reassigns ownership."""
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app_x = AppFactory(owner=owner)
        app_x_id = app_x.app_id
        recipient_id = recipient.user_id

        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from models.app import App

        offer = AppOwnershipService.offer(
            db, app_id=app_x_id, new_owner_id=recipient_id, actor_user_id=owner.user_id
        )

        # Accept with the correct app_id — must succeed.
        result_app, prev_owner_id = AppOwnershipService.accept(
            db,
            collaboration_id=offer.id,
            actor_user_id=recipient_id,
            app_id=app_x_id,  # correct app
        )

        assert result_app.owner_id == recipient_id, (
            "accept(..., app_id=<correct id>) must reassign ownership to the recipient"
        )
        assert prev_owner_id == owner.user_id

        db.expire_all()
        refreshed = db.execute(select(App).where(App.app_id == app_x_id)).scalar_one()
        assert refreshed.owner_id == recipient_id

    def test_accept_with_no_app_id_legacy_path_still_works(self, db):
        """Sanity: accept(..., app_id=None) (the legacy collaboration-respond delegation
        path) still completes successfully — the binding guard must be a no-op when
        app_id is None.
        """
        configure_factories(db)
        owner = UserFactory()
        recipient = UserFactory()
        app = AppFactory(owner=owner)
        app_id = app.app_id
        recipient_id = recipient.user_id

        db.commit()

        from services.app_ownership_service import AppOwnershipService
        from models.app import App

        offer = AppOwnershipService.offer(
            db, app_id=app_id, new_owner_id=recipient_id, actor_user_id=owner.user_id
        )

        # Accept without app_id (None) — legacy path must work.
        result_app, prev_owner_id = AppOwnershipService.accept(
            db,
            collaboration_id=offer.id,
            actor_user_id=recipient_id,
            app_id=None,
        )

        assert result_app.owner_id == recipient_id, (
            "accept(..., app_id=None) must reassign ownership (legacy path must not be broken)"
        )
        assert prev_owner_id == owner.user_id

        db.expire_all()
        refreshed = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed.owner_id == recipient_id
