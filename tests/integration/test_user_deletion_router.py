"""Router-level integration tests for DELETE /internal/admin/users/{id}
and POST /internal/admin/apps/{id}/transfer.

Tests exercise the full FastAPI stack (auth → router → service → DB).
Every test is transactionally isolated via the savepoint-based rollback in conftest.py.

NOTE on Windows skip:
  These tests use the `client` fixture which runs the full FastAPI lifespan.
  `backend/services/file_cleanup_worker.py` imports `fcntl` (Linux-only) at
  module load time, which causes `ModuleNotFoundError` on Windows.  This is a
  pre-existing limitation of the project's `client` fixture on Windows — it
  also affects ALL tests in `tests/integration/routers/`.  The tests are
  marked `skipif sys.platform == 'win32'` so they are skipped on the local
  dev machine but run correctly in the Linux CI environment.

Run (Linux/CI only):
    pytest tests/integration/test_user_deletion_router.py -v
"""

import os
import sys
import pytest
from tests.factories import (
    UserFactory,
    AppFactory,
    configure_factories,
)

# pytest.ini is the active config file; the pytest-env entries in pyproject.toml
# are not read when pytest.ini is present.  Set the minimum required env vars
# explicitly at module level (same pattern as test_local_auth_provisioning.py).
os.environ.setdefault("AICT_LOGIN", "LOCAL")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-minimum-ok")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "postgresql://test_user:test_pass@localhost:5433/test_db")

# The `client` fixture uses the full FastAPI lifespan which imports fcntl (Linux-only).
# Skip the entire module on Windows to avoid ModuleNotFoundError on `fcntl`.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "Router tests require the `client` fixture which triggers a FastAPI lifespan "
        "that imports `fcntl` (Linux-only via file_cleanup_worker.py). Run in CI/Linux."
    ),
)


# ---------------------------------------------------------------------------
# Admin headers fixture — mirrors test_admin_system_embedding_services.py exactly
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_headers(fake_user, db, monkeypatch):
    """Bearer token for fake_user promoted to OMNIADMIN via monkeypatch."""
    from utils.local_auth_tokens import mint_access_token

    monkeypatch.setenv("AICT_OMNIADMINS", fake_user.email)
    db.flush()
    token, _ = mint_access_token(fake_user.user_id, fake_user.email, fake_user.name)
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# DELETE /internal/admin/users/{id}
# ===========================================================================


class TestDeleteUserEndpoint:

    def test_non_admin_gets_403(self, client, auth_headers, fake_user, db):
        """Non-omniadmin caller receives 403 regardless of the target."""
        configure_factories(db)
        target = UserFactory()
        db.flush()

        response = client.delete(
            f"/internal/admin/users/{target.user_id}",
            headers=auth_headers,  # regular user, NOT omniadmin
        )
        assert response.status_code == 403

    def test_unknown_user_returns_404(self, client, admin_headers):
        """Deleting a non-existent user returns 404."""
        response = client.delete(
            "/internal/admin/users/999999",
            headers=admin_headers,
        )
        assert response.status_code == 404

    def test_self_deletion_returns_400(self, client, admin_headers, fake_user):
        """Actor attempting to delete themselves receives 400."""
        response = client.delete(
            f"/internal/admin/users/{fake_user.user_id}",
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_omniadmin_target_returns_403(self, client, admin_headers, db, monkeypatch):
        """Deleting another omniadmin returns 403."""
        configure_factories(db)
        another_admin = UserFactory()
        db.flush()
        # Make another_admin also an omniadmin.
        from utils.config import is_omniadmin

        existing = monkeypatch.getenv("AICT_OMNIADMINS") or ""
        monkeypatch.setenv(
            "AICT_OMNIADMINS",
            ",".join(filter(None, [existing, another_admin.email])),
        )

        response = client.delete(
            f"/internal/admin/users/{another_admin.user_id}",
            headers=admin_headers,
        )
        assert response.status_code == 403

    def test_owned_apps_block_returns_409_with_owned_apps_body(self, client, admin_headers, db):
        """AC-2: mode=block (default) with owned apps returns 409 with owned_apps in body."""
        configure_factories(db)
        target = UserFactory()
        app1 = AppFactory(owner=target)
        app2 = AppFactory(owner=target)
        db.flush()

        response = client.delete(
            f"/internal/admin/users/{target.user_id}",
            headers=admin_headers,
            # No mode → defaults to block
        )
        assert response.status_code == 409
        body = response.json()
        # The 409 detail contains owned_apps summaries.
        detail = body.get("detail", {})
        assert "owned_apps" in detail, f"Expected 'owned_apps' in 409 detail, got: {detail}"
        owned_app_ids = {item["app_id"] for item in detail["owned_apps"]}
        assert app1.app_id in owned_app_ids
        assert app2.app_id in owned_app_ids

    def test_cascade_apps_deletes_user_returns_200(self, client, admin_headers, db, mocker):
        """AC-4: mode=cascade_apps returns 200 and user is gone."""
        configure_factories(db)
        target = UserFactory()
        AppFactory(owner=target)
        db.flush()
        target_id = target.user_id

        # Stub AppService.delete_app to avoid needing Qdrant/pgvector infra.
        def _fake_delete_app(app_id: int) -> bool:
            from models.app import App
            from sqlalchemy import select

            a = db.execute(select(App).where(App.app_id == app_id)).scalar_one_or_none()
            if a:
                db.delete(a)
                db.commit()
                return True
            return False

        mocker.patch("services.app_service.AppService.delete_app", side_effect=_fake_delete_app)

        response = client.delete(
            f"/internal/admin/users/{target_id}",
            json={"mode": "cascade_apps"},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text

        from models.user import User
        from sqlalchemy import select

        db.expire_all()
        assert db.execute(select(User).where(User.user_id == target_id)).scalar_one_or_none() is None

    def test_transfer_apps_returns_200_and_reassigns_owner(self, client, admin_headers, db):
        """AC-3: mode=transfer_apps returns 200 and the app is now owned by the recipient."""
        configure_factories(db)
        target = UserFactory()
        recipient = UserFactory()
        app = AppFactory(owner=target)
        db.flush()
        target_id = target.user_id
        app_id = app.app_id
        recipient_id = recipient.user_id

        response = client.delete(
            f"/internal/admin/users/{target_id}",
            json={"mode": "transfer_apps", "transfer_to_user_id": recipient_id},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text

        from models.user import User
        from models.app import App
        from sqlalchemy import select

        db.expire_all()
        assert db.execute(select(User).where(User.user_id == target_id)).scalar_one_or_none() is None
        refreshed_app = db.execute(select(App).where(App.app_id == app_id)).scalar_one_or_none()
        assert refreshed_app is not None
        assert refreshed_app.owner_id == recipient_id

    def test_no_owned_apps_returns_200(self, client, admin_headers, db):
        """AC-1: deleting a user with no owned apps returns 200."""
        configure_factories(db)
        target = UserFactory()
        db.flush()
        target_id = target.user_id

        response = client.delete(
            f"/internal/admin/users/{target_id}",
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text

        from models.user import User
        from sqlalchemy import select

        db.expire_all()
        assert db.execute(select(User).where(User.user_id == target_id)).scalar_one_or_none() is None

    def test_mode_query_param_fallback_works(self, client, admin_headers, db):
        """mode can be passed as a query parameter when no JSON body is provided."""
        configure_factories(db)
        target = UserFactory()
        app = AppFactory(owner=target)
        db.flush()

        # Using query param fallback instead of JSON body — must still return 409 for block mode.
        response = client.delete(
            f"/internal/admin/users/{target.user_id}?mode=block",
            headers=admin_headers,
        )
        assert response.status_code == 409


# ===========================================================================
# POST /internal/admin/apps/{id}/transfer
# ===========================================================================


class TestTransferAppOwnershipEndpoint:

    def test_non_admin_gets_403(self, client, auth_headers, fake_app, db):
        """Non-omniadmin caller receives 403."""
        configure_factories(db)
        new_owner = UserFactory()
        db.flush()

        response = client.post(
            f"/internal/admin/apps/{fake_app.app_id}/transfer",
            json={"new_owner_id": new_owner.user_id},
            headers=auth_headers,  # regular user
        )
        assert response.status_code == 403

    def test_happy_path_returns_200_with_transfer_summary(self, client, admin_headers, db, fake_app, fake_user):
        """AC-9: successful transfer returns 200 with app_id, previous_owner_id, new_owner_id."""
        configure_factories(db)
        new_owner = UserFactory()
        db.flush()

        response = client.post(
            f"/internal/admin/apps/{fake_app.app_id}/transfer",
            json={"new_owner_id": new_owner.user_id},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["app_id"] == fake_app.app_id
        assert body["new_owner_id"] == new_owner.user_id
        assert body["previous_owner_id"] == fake_user.user_id

    def test_nonexistent_app_returns_404(self, client, admin_headers, db):
        """Non-existent app_id returns 404."""
        configure_factories(db)
        new_owner = UserFactory()
        db.flush()

        response = client.post(
            "/internal/admin/apps/999999/transfer",
            json={"new_owner_id": new_owner.user_id},
            headers=admin_headers,
        )
        assert response.status_code == 404

    def test_inactive_recipient_returns_400(self, client, admin_headers, db, fake_app):
        """Inactive transfer recipient returns 400."""
        configure_factories(db)
        inactive = UserFactory(is_active=False)
        db.flush()

        response = client.post(
            f"/internal/admin/apps/{fake_app.app_id}/transfer",
            json={"new_owner_id": inactive.user_id},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_same_owner_returns_400(self, client, admin_headers, fake_app, fake_user):
        """Transferring to the current owner returns 400."""
        response = client.post(
            f"/internal/admin/apps/{fake_app.app_id}/transfer",
            json={"new_owner_id": fake_user.user_id},
            headers=admin_headers,
        )
        assert response.status_code == 400
