"""Integration tests for UserService.delete_user and AppOwnershipService.transfer_direct.

Maps directly to spec FR-G2 / FR-G3 / FR-G5 and acceptance criteria AC-1..AC-9, AC-13.

Transaction isolation: every test runs in a connection-level savepoint-based
transaction (from conftest.py). Nothing persists between tests.

Run with:
    pytest tests/integration/test_user_deletion.py -v
"""

from datetime import datetime
import pytest
from tests.factories import (
    UserFactory,
    AppFactory,
    APIKeyFactory,
    AppCollaboratorFactory,
    configure_factories,
)


# ---------------------------------------------------------------------------
# Module-level admin_headers fixture (mirrors test_admin_system_embedding_services.py)
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_headers(fake_user, db, monkeypatch):
    """Auth headers for fake_user promoted to OMNIADMIN via monkeypatch."""
    from utils.local_auth_tokens import mint_access_token

    monkeypatch.setenv("AICT_OMNIADMINS", fake_user.email)
    db.flush()
    token, _ = mint_access_token(fake_user.user_id, fake_user.email, fake_user.name)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helper: create a user with a UserCredential and RefreshToken in a transaction
# ---------------------------------------------------------------------------


def _add_credential(db, user):
    """Attach a UserCredential row to *user* and flush."""
    from models.user_credential import UserCredential

    cred = UserCredential(
        user_id=user.user_id,
        hashed_password="$2b$12$fakehash",
        is_verified=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(cred)
    db.flush()
    return cred


def _add_refresh_token(db, user):
    """Attach a RefreshToken row to *user* and flush."""
    from models.refresh_token import RefreshToken
    from datetime import timezone

    rt = RefreshToken(
        user_id=user.user_id,
        jti="test-jti-" + str(user.user_id),
        family_id="test-family-" + str(user.user_id),
        token_hash="aaaa" * 32,  # 128 hex chars
        expires_at=datetime.now(timezone.utc),
    )
    db.add(rt)
    db.flush()
    return rt


def _add_subscription(db, user):
    """Attach a Subscription row to *user* and flush."""
    from models.subscription import Subscription, SubscriptionTier, BillingStatus

    sub = Subscription(
        user_id=user.user_id,
        tier=SubscriptionTier.FREE,
        billing_status=BillingStatus.NONE,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(sub)
    db.flush()
    return sub


def _add_conversation(db, agent, user):
    """Attach a Conversation row and flush."""
    from models.conversation import Conversation, ConversationSource

    conv = Conversation(
        agent_id=agent.agent_id,
        user_id=user.user_id,
        session_id=f"conv-test-{user.user_id}-{agent.agent_id}",
        source=ConversationSource.PLAYGROUND,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(conv)
    db.flush()
    return conv


def _add_crawl_job(db, domain, user):
    """Attach a CrawlJob row triggered by *user* and flush."""
    from models.crawl_job import CrawlJob
    from models.enums.crawl_job_status import CrawlJobStatus
    from models.enums.crawl_trigger import CrawlTrigger

    job = CrawlJob(
        domain_id=domain.domain_id,
        status=CrawlJobStatus.QUEUED,
        triggered_by=CrawlTrigger.MANUAL,
        triggered_by_user_id=user.user_id,
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    return job


# ===========================================================================
# AC-1 — REGRESSION: class-A rows (credentials/refresh_tokens/subscription)
#          no longer cause NotNullViolation on delete_user
# ===========================================================================


class TestDeleteUserClassA:
    """Regression test: AC-1.

    This was the original reported bug — deleting a user with only a credential
    (+ refresh token + subscription) raised NotNullViolation because the ORM
    tried to emit UPDATE user_credentials SET user_id = NULL before the DB delete.
    """

    def test_delete_user_with_credential_and_refresh_token_succeeds(self, db):
        """AC-1: no-data user with class-A rows deletes cleanly (no NotNullViolation).

        Reproduce-first: before the fix this test raised psycopg2 IntegrityError.
        After the fix it must return True and leave no orphaned rows.
        """
        configure_factories(db)
        # Actor is a different user so self-deletion guardrail does not fire.
        actor = UserFactory()
        target = UserFactory()
        target_id = target.user_id

        # Attach class-A rows
        cred = _add_credential(db, target)
        cred_id = cred.id
        rt = _add_refresh_token(db, target)
        rt_id = rt.id
        sub = _add_subscription(db, target)
        sub_id = sub.id

        from services.user_service import UserService

        result = UserService.delete_user(
            db,
            target_id,
            actor_user_id=actor.user_id,
            mode="block",
        )

        assert result is True

        # Class-A rows must be gone (DB CASCADE removed them with the user row).
        from models.user_credential import UserCredential
        from models.refresh_token import RefreshToken
        from models.subscription import Subscription
        from models.user import User
        from sqlalchemy import select

        db.expire_all()
        assert db.execute(select(User).where(User.user_id == target_id)).scalar_one_or_none() is None
        assert db.execute(select(UserCredential).where(UserCredential.id == cred_id)).scalar_one_or_none() is None
        assert db.execute(select(RefreshToken).where(RefreshToken.id == rt_id)).scalar_one_or_none() is None
        assert db.execute(select(Subscription).where(Subscription.id == sub_id)).scalar_one_or_none() is None


# ===========================================================================
# AC-2 — Owned apps + mode=block → 409 / OwnedAppsPresentError, no mutation
# ===========================================================================


class TestDeleteUserBlockMode:

    def test_block_raises_owned_apps_present_error_with_summaries(self, db):
        """AC-2: mode=block raises OwnedAppsPresentError carrying the owned-app list."""
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()
        app1 = AppFactory(owner=target)
        app2 = AppFactory(owner=target)
        target_id = target.user_id

        from services.user_service import UserService
        from services.user_deletion_errors import OwnedAppsPresentError

        with pytest.raises(OwnedAppsPresentError) as exc_info:
            UserService.delete_user(db, target_id, actor_user_id=actor.user_id, mode="block")

        err = exc_info.value
        app_ids_in_error = {s["app_id"] for s in err.owned_apps}
        assert app1.app_id in app_ids_in_error
        assert app2.app_id in app_ids_in_error

        # No mutation: user and apps still exist.
        from models.user import User
        from models.app import App
        from sqlalchemy import select

        db.expire_all()
        assert db.execute(select(User).where(User.user_id == target_id)).scalar_one_or_none() is not None
        assert db.execute(select(App).where(App.app_id == app1.app_id)).scalar_one_or_none() is not None
        assert db.execute(select(App).where(App.app_id == app2.app_id)).scalar_one_or_none() is not None

    def test_block_no_apps_succeeds(self, db):
        """Sanity: mode=block with zero owned apps deletes the user normally."""
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()
        target_id = target.user_id

        from services.user_service import UserService

        result = UserService.delete_user(db, target_id, actor_user_id=actor.user_id, mode="block")
        assert result is True

        from models.user import User
        from sqlalchemy import select

        db.expire_all()
        assert db.execute(select(User).where(User.user_id == target_id)).scalar_one_or_none() is None


# ===========================================================================
# AC-4 — Owned apps + mode=cascade_apps → apps deleted, user deleted
# ===========================================================================


class TestDeleteUserCascadeApps:

    def test_cascade_apps_deletes_owned_apps_and_user(self, db, mocker):
        """AC-4: mode=cascade_apps calls AppService.delete_app per owned app then deletes user."""
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()
        app1 = AppFactory(owner=target)
        app2 = AppFactory(owner=target)
        target_id = target.user_id

        # Spy on AppService.delete_app to track calls without actually running the
        # full vector-store teardown (which requires Qdrant/pgvector infra).
        # We replace delete_app with a version that deletes the App row directly.
        deleted_app_ids = []

        def _fake_delete_app(app_id: int) -> bool:
            from models.app import App
            from sqlalchemy import select

            a = db.execute(select(App).where(App.app_id == app_id)).scalar_one_or_none()
            if a:
                db.delete(a)
                db.commit()
                deleted_app_ids.append(app_id)
                return True
            return False

        mocker.patch("services.app_service.AppService.delete_app", side_effect=_fake_delete_app)

        from services.user_service import UserService

        result = UserService.delete_user(db, target_id, actor_user_id=actor.user_id, mode="cascade_apps")
        assert result is True

        assert app1.app_id in deleted_app_ids
        assert app2.app_id in deleted_app_ids

        from models.user import User
        from sqlalchemy import select

        db.expire_all()
        assert db.execute(select(User).where(User.user_id == target_id)).scalar_one_or_none() is None


# ===========================================================================
# AC-3 — Owned apps + mode=transfer_apps → owner reassigned, user deleted
# ===========================================================================


class TestDeleteUserTransferApps:

    def test_transfer_apps_reassigns_owner_and_deletes_user(self, db):
        """AC-3: mode=transfer_apps transfers owned apps to recipient then deletes user."""
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()
        recipient = UserFactory()
        app1 = AppFactory(owner=target)
        app2 = AppFactory(owner=target)
        app1_id = app1.app_id
        app2_id = app2.app_id
        target_id = target.user_id
        recipient_id = recipient.user_id

        from services.user_service import UserService

        result = UserService.delete_user(
            db,
            target_id,
            actor_user_id=actor.user_id,
            mode="transfer_apps",
            transfer_to_user_id=recipient_id,
        )
        assert result is True

        from models.user import User
        from models.app import App
        from sqlalchemy import select

        db.expire_all()
        # User gone
        assert db.execute(select(User).where(User.user_id == target_id)).scalar_one_or_none() is None
        # Apps still exist, now owned by recipient
        app1_after = db.execute(select(App).where(App.app_id == app1_id)).scalar_one_or_none()
        app2_after = db.execute(select(App).where(App.app_id == app2_id)).scalar_one_or_none()
        assert app1_after is not None
        assert app2_after is not None
        assert app1_after.owner_id == recipient_id
        assert app2_after.owner_id == recipient_id

    def test_transfer_apps_no_transfer_id_raises(self, db):
        """transfer_apps without transfer_to_user_id raises TransferRecipientInvalidError."""
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()
        AppFactory(owner=target)

        from services.user_service import UserService
        from services.app_ownership_errors import TransferRecipientInvalidError

        with pytest.raises(TransferRecipientInvalidError):
            UserService.delete_user(
                db,
                target.user_id,
                actor_user_id=actor.user_id,
                mode="transfer_apps",
                transfer_to_user_id=None,
            )

    def test_transfer_apps_same_as_target_raises(self, db):
        """transfer_to_user_id == user_id being deleted raises TransferRecipientInvalidError."""
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()
        AppFactory(owner=target)

        from services.user_service import UserService
        from services.app_ownership_errors import TransferRecipientInvalidError

        with pytest.raises(TransferRecipientInvalidError):
            UserService.delete_user(
                db,
                target.user_id,
                actor_user_id=actor.user_id,
                mode="transfer_apps",
                transfer_to_user_id=target.user_id,
            )

    def test_transfer_apps_nonexistent_recipient_raises(self, db):
        """Non-existent transfer recipient raises TransferRecipientInvalidError."""
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()
        AppFactory(owner=target)

        from services.user_service import UserService
        from services.app_ownership_errors import TransferRecipientInvalidError

        with pytest.raises(TransferRecipientInvalidError):
            UserService.delete_user(
                db,
                target.user_id,
                actor_user_id=actor.user_id,
                mode="transfer_apps",
                transfer_to_user_id=999999,
            )

    def test_transfer_apps_inactive_recipient_raises(self, db):
        """Inactive transfer recipient raises TransferRecipientInvalidError."""
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()
        AppFactory(owner=target)
        recipient = UserFactory(is_active=False)

        from services.user_service import UserService
        from services.app_ownership_errors import TransferRecipientInvalidError

        with pytest.raises(TransferRecipientInvalidError):
            UserService.delete_user(
                db,
                target.user_id,
                actor_user_id=actor.user_id,
                mode="transfer_apps",
                transfer_to_user_id=recipient.user_id,
            )


# ===========================================================================
# AC-5 — Guardrails: omniadmin / self / unknown
# ===========================================================================


class TestDeleteUserGuardrails:

    def test_omniadmin_target_raises_omniadmin_deletion_error(self, db, monkeypatch):
        """AC-5: deleting an omniadmin raises OmniadminDeletionError (→ 403)."""
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()
        # Make the target an omniadmin.
        monkeypatch.setenv("AICT_OMNIADMINS", target.email)

        from services.user_service import UserService
        from services.user_deletion_errors import OmniadminDeletionError

        with pytest.raises(OmniadminDeletionError):
            UserService.delete_user(db, target.user_id, actor_user_id=actor.user_id)

    def test_self_deletion_raises_self_deletion_error(self, db):
        """AC-5: actor == target raises SelfDeletionError (→ 400)."""
        configure_factories(db)
        target = UserFactory()

        from services.user_service import UserService
        from services.user_deletion_errors import SelfDeletionError

        with pytest.raises(SelfDeletionError):
            UserService.delete_user(db, target.user_id, actor_user_id=target.user_id)

    def test_unknown_user_raises_user_not_found_error(self, db):
        """AC-5: unknown user_id raises UserNotFoundError (→ 404)."""
        configure_factories(db)
        actor = UserFactory()

        from services.user_service import UserService
        from services.user_deletion_errors import UserNotFoundError

        with pytest.raises(UserNotFoundError):
            UserService.delete_user(db, 999999, actor_user_id=actor.user_id)

    def test_guardrails_make_no_mutation_on_rejection(self, db, monkeypatch):
        """All guardrails leave the database unchanged."""
        configure_factories(db)
        target = UserFactory()
        monkeypatch.setenv("AICT_OMNIADMINS", target.email)

        from services.user_service import UserService
        from services.user_deletion_errors import OmniadminDeletionError
        from models.user import User
        from sqlalchemy import select

        with pytest.raises(OmniadminDeletionError):
            UserService.delete_user(db, target.user_id, actor_user_id=target.user_id + 1)

        db.expire_all()
        assert db.execute(select(User).where(User.user_id == target.user_id)).scalar_one_or_none() is not None


# ===========================================================================
# AC-6 — Class-C / invited-by (SET NULL) semantics
# ===========================================================================


class TestDeleteUserClassC:

    def test_user_collaboration_memberships_removed_on_delete(self, db):
        """AC-6: a user's AppCollaborator rows (user_id) are removed on deletion."""
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()
        app_owner = UserFactory()
        app = AppFactory(owner=app_owner)

        # Target is a collaborator on another user's app.
        collab = AppCollaboratorFactory(app=app, user=target)
        collab_id = collab.id

        from services.user_service import UserService

        UserService.delete_user(db, target.user_id, actor_user_id=actor.user_id, mode="block")

        from models.app_collaborator import AppCollaborator
        from sqlalchemy import select

        db.expire_all()
        # The membership row must be gone (class-C explicit removal).
        assert db.execute(
            select(AppCollaborator).where(AppCollaborator.id == collab_id)
        ).scalar_one_or_none() is None

    def test_invited_by_set_null_on_delete_collaboration_survives(self, db):
        """AC-6: invited_by rows created by the target user get SET NULL; those collaborations survive."""
        configure_factories(db)
        actor = UserFactory()
        inviter = UserFactory()  # This user will be deleted
        invitee = UserFactory()
        app_owner = UserFactory()
        app = AppFactory(owner=app_owner)

        # invitee was invited BY inviter — this is a class-D row (invited_by = inviter.user_id).
        collab = AppCollaboratorFactory(app=app, user=invitee, invited_by=inviter.user_id)
        collab_id = collab.id

        from services.user_service import UserService

        UserService.delete_user(db, inviter.user_id, actor_user_id=actor.user_id, mode="block")

        from models.app_collaborator import AppCollaborator
        from sqlalchemy import select

        db.expire_all()
        # The collaboration of invitee must SURVIVE (row still present).
        surviving = db.execute(
            select(AppCollaborator).where(AppCollaborator.id == collab_id)
        ).scalar_one_or_none()
        assert surviving is not None
        # invited_by must be NULL (SET NULL FK rule).
        assert surviving.invited_by is None

    def test_user_api_keys_in_non_owned_apps_deleted(self, db):
        """AC-8: API keys owned by the user in apps they don't own are removed."""
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()
        other_owner = UserFactory()
        other_app = AppFactory(owner=other_owner)

        # The target holds an API key in an app they do NOT own.
        key = APIKeyFactory(app=other_app, user=target)
        key_id = key.key_id

        from services.user_service import UserService

        UserService.delete_user(db, target.user_id, actor_user_id=actor.user_id, mode="block")

        from models.api_key import APIKey
        from sqlalchemy import select

        db.expire_all()
        assert db.execute(select(APIKey).where(APIKey.key_id == key_id)).scalar_one_or_none() is None


# ===========================================================================
# AC-7 — Class-D: conversations and crawl_jobs survive with user_id = NULL
# ===========================================================================


class TestDeleteUserClassD:

    def test_conversation_user_id_set_null_row_survives(self, db, fake_agent):
        """AC-7: Conversation.user_id is set to NULL; the row survives."""
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()

        conv = _add_conversation(db, fake_agent, target)
        conv_id = conv.conversation_id

        from services.user_service import UserService

        UserService.delete_user(db, target.user_id, actor_user_id=actor.user_id, mode="block")

        from models.conversation import Conversation
        from sqlalchemy import select

        db.expire_all()
        surviving = db.execute(
            select(Conversation).where(Conversation.conversation_id == conv_id)
        ).scalar_one_or_none()
        assert surviving is not None
        assert surviving.user_id is None

    def test_crawl_job_triggered_by_set_null_row_survives(self, db, fake_domain):
        """AC-7: crawl_job.triggered_by_user_id is set to NULL; the row survives."""
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()

        job = _add_crawl_job(db, fake_domain, target)
        job_id = job.id

        from services.user_service import UserService

        UserService.delete_user(db, target.user_id, actor_user_id=actor.user_id, mode="block")

        from models.crawl_job import CrawlJob
        from sqlalchemy import select

        db.expire_all()
        surviving = db.execute(select(CrawlJob).where(CrawlJob.id == job_id)).scalar_one_or_none()
        assert surviving is not None
        assert surviving.triggered_by_user_id is None


# ===========================================================================
# FR-G3 / AC-9 — AppOwnershipService.transfer_direct
# ===========================================================================


class TestTransferDirect:

    def test_happy_path_reassigns_owner(self, db):
        """AC-9: transfer_direct reassigns owner_id to recipient."""
        configure_factories(db)
        actor = UserFactory()
        old_owner = UserFactory()
        new_owner = UserFactory()
        app = AppFactory(owner=old_owner)
        app_id = app.app_id
        old_owner_id = old_owner.user_id
        new_owner_id = new_owner.user_id

        from services.app_ownership_service import AppOwnershipService

        result_app, prev_owner_id = AppOwnershipService.transfer_direct(
            db, app_id=app_id, new_owner_id=new_owner_id, actor_user_id=actor.user_id
        )

        assert result_app.owner_id == new_owner_id
        assert prev_owner_id == old_owner_id

        from models.app import App
        from sqlalchemy import select

        db.expire_all()
        refreshed = db.execute(select(App).where(App.app_id == app_id)).scalar_one()
        assert refreshed.owner_id == new_owner_id

    def test_nonexistent_app_raises_app_not_found_error(self, db):
        """AC-9: nonexistent app_id raises AppNotFoundError (→ 404)."""
        configure_factories(db)
        actor = UserFactory()
        new_owner = UserFactory()

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import AppNotFoundError

        with pytest.raises(AppNotFoundError):
            AppOwnershipService.transfer_direct(
                db, app_id=999999, new_owner_id=new_owner.user_id, actor_user_id=actor.user_id
            )

    def test_inactive_recipient_raises_transfer_recipient_invalid_error(self, db):
        """AC-9: inactive recipient raises TransferRecipientInvalidError (→ 400)."""
        configure_factories(db)
        actor = UserFactory()
        owner = UserFactory()
        app = AppFactory(owner=owner)
        inactive_user = UserFactory(is_active=False)

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import TransferRecipientInvalidError

        with pytest.raises(TransferRecipientInvalidError):
            AppOwnershipService.transfer_direct(
                db, app_id=app.app_id, new_owner_id=inactive_user.user_id, actor_user_id=actor.user_id
            )

    def test_same_as_current_owner_raises_transfer_recipient_invalid_error(self, db):
        """AC-9: transferring to the current owner raises TransferRecipientInvalidError."""
        configure_factories(db)
        actor = UserFactory()
        owner = UserFactory()
        app = AppFactory(owner=owner)

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import TransferRecipientInvalidError

        with pytest.raises(TransferRecipientInvalidError):
            AppOwnershipService.transfer_direct(
                db, app_id=app.app_id, new_owner_id=owner.user_id, actor_user_id=actor.user_id
            )

    def test_nonexistent_recipient_raises_transfer_recipient_invalid_error(self, db):
        """Non-existent recipient raises TransferRecipientInvalidError (→ 400)."""
        configure_factories(db)
        actor = UserFactory()
        owner = UserFactory()
        app = AppFactory(owner=owner)

        from services.app_ownership_service import AppOwnershipService
        from services.app_ownership_errors import TransferRecipientInvalidError

        with pytest.raises(TransferRecipientInvalidError):
            AppOwnershipService.transfer_direct(
                db, app_id=app.app_id, new_owner_id=999999, actor_user_id=actor.user_id
            )

    def test_collaborator_row_removed_for_new_owner(self, db):
        """FR-C5: if the recipient already had a collaborator row it is removed on transfer."""
        configure_factories(db)
        actor = UserFactory()
        owner = UserFactory()
        new_owner = UserFactory()
        app = AppFactory(owner=owner)

        # New owner already has a collaborator row on this app.
        collab = AppCollaboratorFactory(app=app, user=new_owner)
        collab_id = collab.id

        from services.app_ownership_service import AppOwnershipService

        AppOwnershipService.transfer_direct(
            db, app_id=app.app_id, new_owner_id=new_owner.user_id, actor_user_id=actor.user_id
        )

        from models.app_collaborator import AppCollaborator
        from sqlalchemy import select

        db.expire_all()
        # The old collaborator row must be gone — ownership supersedes collaboration.
        assert db.execute(
            select(AppCollaborator).where(AppCollaborator.id == collab_id)
        ).scalar_one_or_none() is None


# ===========================================================================
# AC-13 — Atomicity: failure mid-cascade / mid-transfer rolls back
# ===========================================================================


class TestAtomicity:

    def test_cascade_apps_failure_on_second_app_leaves_user_present(self, db, mocker):
        """AC-13 (cascade_apps path): if delete_app raises on the second app, the user is still present.

        AD-2 guarantees that the user row is deleted LAST. A mid-loop failure
        therefore leaves the user intact; the operation is resumable.
        """
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()
        app1 = AppFactory(owner=target)
        app2 = AppFactory(owner=target)
        app1_id = app1.app_id
        app2_id = app2.app_id
        target_id = target.user_id

        call_count = {"n": 0}

        def _failing_delete_app(app_id: int) -> bool:
            call_count["n"] += 1
            from models.app import App
            from sqlalchemy import select

            if call_count["n"] == 1:
                # First app deletes OK.
                a = db.execute(select(App).where(App.app_id == app_id)).scalar_one_or_none()
                if a:
                    db.delete(a)
                    db.commit()
                    return True
                return False
            else:
                # Second app raises — simulates an error mid-cascade.
                raise RuntimeError("Simulated delete_app failure on second app")

        mocker.patch("services.app_service.AppService.delete_app", side_effect=_failing_delete_app)

        from services.user_service import UserService

        with pytest.raises(RuntimeError, match="Simulated"):
            UserService.delete_user(
                db, target_id, actor_user_id=actor.user_id, mode="cascade_apps"
            )

        # User must still exist (resumable guarantee — delete_user aborts before db.delete(user)).
        from models.user import User
        from sqlalchemy import select

        db.expire_all()
        user_after = db.execute(select(User).where(User.user_id == target_id)).scalar_one_or_none()
        assert user_after is not None, (
            "User should still exist after mid-cascade failure (AD-2 resumable guarantee)"
        )

    def test_transfer_apps_failure_mid_loop_rolls_back_all_transfers(self, db, mocker):
        """AC-13 (transfer_apps path): failure during _reassign_owner must roll back all staged transfers.

        The transfer_apps loop is guarded by a try/except that calls db.rollback()
        on any mid-loop failure (AD-2: all reassignments + the user deletion form one
        atomic transaction). After a failure on app N, both apps remain owned by the
        original target and the user still exists — no observable partial state.
        """
        configure_factories(db)
        actor = UserFactory()
        target = UserFactory()
        recipient = UserFactory()
        app1 = AppFactory(owner=target)
        app2 = AppFactory(owner=target)
        app1_id = app1.app_id
        app2_id = app2.app_id
        target_id = target.user_id
        recipient_id = recipient.user_id

        # Commit the setup so the service's atomic db.rollback() on mid-loop failure
        # reverts ONLY the staged transfers (to this savepoint), not the fixture data.
        # The db fixture uses join_transaction_mode="create_savepoint", so this commit
        # advances the savepoint past the setup without breaking per-test isolation.
        db.commit()

        call_count = {"n": 0}

        from services import app_ownership_service as _aosvc

        original_reassign = _aosvc.AppOwnershipService._reassign_owner

        def _partial_fail_reassign(db_inner, app, new_owner_id, *, actor_user_id):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("Simulated _reassign_owner failure on second app")
            original_reassign(db_inner, app, new_owner_id, actor_user_id=actor_user_id)

        mocker.patch.object(
            _aosvc.AppOwnershipService,
            "_reassign_owner",
            side_effect=_partial_fail_reassign,
        )

        from services.user_service import UserService

        with pytest.raises(RuntimeError, match="Simulated"):
            UserService.delete_user(
                db,
                target_id,
                actor_user_id=actor.user_id,
                mode="transfer_apps",
                transfer_to_user_id=recipient_id,
            )

        # Expected (per AC-13): user still exists, both apps still owned by original target.
        from models.user import User
        from models.app import App
        from sqlalchemy import select

        db.expire_all()
        assert db.execute(select(User).where(User.user_id == target_id)).scalar_one_or_none() is not None
        a1 = db.execute(select(App).where(App.app_id == app1_id)).scalar_one_or_none()
        a2 = db.execute(select(App).where(App.app_id == app2_id)).scalar_one_or_none()
        assert a1 is not None
        assert a2 is not None
        # Both apps must still be owned by the original target — the rollback reverted
        # the first app's staged owner_id change.
        assert a1.owner_id == target_id, f"app1 owner should still be target; got {a1.owner_id}"
        assert a2.owner_id == target_id, f"app2 owner should still be target; got {a2.owner_id}"
