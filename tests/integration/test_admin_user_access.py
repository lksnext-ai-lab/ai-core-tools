"""Integration tests for platform-admin app and API-key access controls."""

import os
import sys

import pytest

from tests.factories import (
    APIKeyFactory,
    AppCollaboratorFactory,
    AppFactory,
    UserFactory,
    configure_factories,
)

os.environ.setdefault("AICT_LOGIN", "LOCAL")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-minimum-ok")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "postgresql://test_user:test_pass@localhost:5433/test_db")

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="The full FastAPI client lifespan imports fcntl on Windows.",
)


@pytest.fixture
def admin_headers(fake_user, db, monkeypatch):
    from utils.local_auth_tokens import mint_access_token

    monkeypatch.setenv("AICT_OMNIADMINS", fake_user.email)
    db.flush()
    token, _ = mint_access_token(fake_user.user_id, fake_user.email, fake_user.name)
    return {"Authorization": f"Bearer {token}"}


def test_admin_grants_and_removes_app_access_without_invitation(client, admin_headers, db):
    configure_factories(db)
    owner = UserFactory()
    target = UserFactory()
    app = AppFactory(owner=owner)
    db.flush()

    from models.app_collaborator import (
        AppCollaborator,
        CollaborationRole,
        CollaborationStatus,
    )

    AppCollaboratorFactory(
        app=app,
        user=target,
        role=CollaborationRole.OWNER,
        status=CollaborationStatus.PENDING,
        invited_by=owner.user_id,
    )
    db.flush()

    response = client.put(
        f"/internal/admin/users/{target.user_id}/apps/{app.app_id}",
        json={"role": "administrator"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["role"] == "administrator"

    membership = db.query(AppCollaborator).filter_by(
        app_id=app.app_id,
        user_id=target.user_id,
        role=CollaborationRole.ADMINISTRATOR,
    ).one()
    assert membership.status == CollaborationStatus.ACCEPTED
    assert membership.accepted_at is not None
    assert db.query(AppCollaborator).filter_by(
        app_id=app.app_id,
        user_id=target.user_id,
    ).count() == 2

    response = client.delete(
        f"/internal/admin/users/{target.user_id}/apps/{app.app_id}",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert db.query(AppCollaborator).filter_by(
        app_id=app.app_id,
        user_id=target.user_id,
    ).count() == 0


def test_admin_cannot_grant_privileged_app_role_to_platform_viewer(client, admin_headers, db):
    configure_factories(db)
    target = UserFactory(platform_role="viewer")
    app = AppFactory()
    db.flush()

    response = client.put(
        f"/internal/admin/users/{target.user_id}/apps/{app.app_id}",
        json={"role": "administrator"},
        headers=admin_headers,
    )
    assert response.status_code == 400

    response = client.put(
        f"/internal/admin/users/{target.user_id}/apps/{app.app_id}",
        json={"role": "viewer"},
        headers=admin_headers,
    )
    assert response.status_code == 200


def test_admin_access_endpoints_protect_self_and_omniadmin_targets(
    client, admin_headers, fake_user, db, monkeypatch
):
    configure_factories(db)
    protected = UserFactory()
    monkeypatch.setenv("AICT_OMNIADMINS", f"{fake_user.email},{protected.email}")

    for target in (fake_user, protected):
        response = client.put(
            f"/internal/admin/users/{target.user_id}/apps/1",
            json={"role": "viewer"},
            headers=admin_headers,
        )
        assert response.status_code == 403

        response = client.delete(
            f"/internal/admin/users/{target.user_id}/apps/1",
            headers=admin_headers,
        )
        assert response.status_code == 403

        response = client.patch(
            f"/internal/admin/users/{target.user_id}/api-keys/1",
            json={"is_active": False},
            headers=admin_headers,
        )
        assert response.status_code == 403


def test_admin_changes_api_key_status_only_for_key_owner(client, admin_headers, db):
    configure_factories(db)
    target = UserFactory()
    other_user = UserFactory()
    app = AppFactory()
    target_key = APIKeyFactory(user=target, app=app, is_active=True)
    other_key = APIKeyFactory(user=other_user, app=app, is_active=True)
    db.flush()

    response = client.patch(
        f"/internal/admin/users/{target.user_id}/api-keys/{target_key.key_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    db.refresh(target_key)
    assert target_key.is_active is False

    response = client.patch(
        f"/internal/admin/users/{target.user_id}/api-keys/{other_key.key_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert response.status_code == 404
    db.refresh(other_key)
    assert other_key.is_active is True
