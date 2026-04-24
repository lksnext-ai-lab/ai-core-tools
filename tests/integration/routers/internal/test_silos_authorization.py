"""
Security tests for silo endpoints authorization (BOLA/IDOR prevention).

Validates:
  - Users without a role on an app cannot access its silo search or delete endpoints
  - Role requirements are enforced (viewer for read, editor for delete)
  - Cross-app access is denied
"""

import pytest
from datetime import datetime

from models.silo import Silo
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from tests.factories import (
    configure_factories,
    UserFactory,
    AppFactory,
    AppCollaboratorFactory,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_silo(db, fake_app):
    """A test Silo linked to fake_app."""
    silo = Silo(
        name="Test Silo",
        description="Silo for auth testing",
        silo_type="CUSTOM",
        app_id=fake_app.app_id,
    )
    db.add(silo)
    db.flush()
    return silo


@pytest.fixture
def setup_cross_app_silo(db, fake_user, fake_app):
    """
    Create a second app with its own silo, owned by a different user.
    Returns (other_app, other_silo, other_user).
    """
    configure_factories(db)
    other_user = UserFactory(email="other-silo@mattin-test.com", name="Other Silo User")
    other_app = AppFactory(owner=other_user)
    other_silo = Silo(
        name="Other Silo",
        description="Silo in another app",
        silo_type="CUSTOM",
        app_id=other_app.app_id,
    )
    db.add(other_silo)
    db.flush()
    return other_app, other_silo, other_user


@pytest.fixture
def unrelated_user_headers(db, client, setup_cross_app_silo):
    """Auth headers for a user who has NO role on the main fake_app."""
    _, _, other_user = setup_cross_app_silo
    db.flush()
    response = client.post(
        "/internal/auth/dev-login",
        json={"email": other_user.email},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def viewer_headers(db, client, fake_app, fake_user):
    """Auth headers for a user with VIEWER role on fake_app."""
    configure_factories(db)
    viewer_user = UserFactory(email="viewer-silo@mattin-test.com", name="Viewer User")
    collab = AppCollaborator(
        app_id=fake_app.app_id,
        user_id=viewer_user.user_id,
        role=CollaborationRole.VIEWER,
        status=CollaborationStatus.ACCEPTED,
        invited_by=fake_user.user_id,
        invited_at=datetime.now(),
        accepted_at=datetime.now(),
    )
    db.add(collab)
    db.flush()
    response = client.post(
        "/internal/auth/dev-login",
        json={"email": viewer_user.email},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def editor_headers(db, client, fake_app, fake_user):
    """Auth headers for a user with EDITOR role on fake_app."""
    configure_factories(db)
    editor_user = UserFactory(email="editor-silo@mattin-test.com", name="Editor User")
    collab = AppCollaborator(
        app_id=fake_app.app_id,
        user_id=editor_user.user_id,
        role=CollaborationRole.EDITOR,
        status=CollaborationStatus.ACCEPTED,
        invited_by=fake_user.user_id,
        invited_at=datetime.now(),
        accepted_at=datetime.now(),
    )
    db.add(collab)
    db.flush()
    response = client.post(
        "/internal/auth/dev-login",
        json={"email": editor_user.email},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test: require_min_role enforced on silo search
# ---------------------------------------------------------------------------

class TestSiloSearchAuthorization:
    """POST /internal/apps/{app_id}/silos/{silo_id}/search"""

    def test_search_requires_role(
        self, client, fake_app, fake_silo, unrelated_user_headers, db
    ):
        """User without role on app gets 403 when searching silo documents."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/silos/{fake_silo.silo_id}/search",
            json={"query": "test search", "limit": 5},
            headers=unrelated_user_headers,
        )
        assert response.status_code == 403

    def test_search_accessible_by_viewer(
        self, client, fake_app, fake_silo, viewer_headers, db
    ):
        """Viewer can search silo documents (may fail downstream, but not with 403)."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/silos/{fake_silo.silo_id}/search",
            json={"query": "test search", "limit": 5},
            headers=viewer_headers,
        )
        assert response.status_code != 403


# ---------------------------------------------------------------------------
# Test: require_min_role enforced on silo document deletion
# ---------------------------------------------------------------------------

class TestSiloDeleteDocumentsAuthorization:
    """DELETE /internal/apps/{app_id}/silos/{silo_id}/documents"""

    def test_delete_documents_requires_role(
        self, client, fake_app, fake_silo, unrelated_user_headers, db
    ):
        """User without role on app gets 403 when deleting silo documents."""
        db.flush()
        response = client.request(
            "DELETE",
            f"/internal/apps/{fake_app.app_id}/silos/{fake_silo.silo_id}/documents",
            json={"document_ids": ["fake-doc-id"]},
            headers=unrelated_user_headers,
        )
        assert response.status_code == 403

    def test_delete_documents_viewer_gets_403(
        self, client, fake_app, fake_silo, viewer_headers, db
    ):
        """Viewer role is insufficient for delete (requires editor)."""
        db.flush()
        response = client.request(
            "DELETE",
            f"/internal/apps/{fake_app.app_id}/silos/{fake_silo.silo_id}/documents",
            json={"document_ids": ["fake-doc-id"]},
            headers=viewer_headers,
        )
        assert response.status_code == 403

    def test_delete_documents_accessible_by_editor(
        self, client, fake_app, fake_silo, editor_headers, db
    ):
        """Editor can delete silo documents (may fail downstream, but not with 403)."""
        db.flush()
        response = client.request(
            "DELETE",
            f"/internal/apps/{fake_app.app_id}/silos/{fake_silo.silo_id}/documents",
            json={"document_ids": ["fake-doc-id"]},
            headers=editor_headers,
        )
        assert response.status_code != 403


# ---------------------------------------------------------------------------
# Test: cross-app IDOR prevention
# ---------------------------------------------------------------------------

class TestSiloCrossAppAccess:
    """Verify user can't access silos from an app they don't have access to."""

    def test_search_cross_app_denied(
        self, client, auth_headers, setup_cross_app_silo, db
    ):
        """
        auth_headers user (fake_user) has no role on other_app,
        so searching other_app's silo should return 403.
        """
        other_app, other_silo, _ = setup_cross_app_silo
        db.flush()
        response = client.post(
            f"/internal/apps/{other_app.app_id}/silos/{other_silo.silo_id}/search",
            json={"query": "test", "limit": 5},
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_delete_cross_app_denied(
        self, client, auth_headers, setup_cross_app_silo, db
    ):
        """
        auth_headers user (fake_user) has no role on other_app,
        so deleting from other_app's silo should return 403.
        """
        other_app, other_silo, _ = setup_cross_app_silo
        db.flush()
        response = client.request(
            "DELETE",
            f"/internal/apps/{other_app.app_id}/silos/{other_silo.silo_id}/documents",
            json={"document_ids": ["fake-doc-id"]},
            headers=auth_headers,
        )
        assert response.status_code == 403
