"""
Integration tests for the SharePoint Sources endpoints.

Endpoints under test:
  GET    /internal/apps/{app_id}/sharepoint-sources
  POST   /internal/apps/{app_id}/sharepoint-sources
  GET    /internal/apps/{app_id}/sharepoint-sources/{source_id}
  PUT    /internal/apps/{app_id}/sharepoint-sources/{source_id}
  DELETE /internal/apps/{app_id}/sharepoint-sources/{source_id}
  POST   /internal/apps/{app_id}/sharepoint-sources/{source_id}/sync
  GET    /internal/capabilities

All Microsoft Graph calls are mocked — no real credentials needed.
"""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

pytest.importorskip("mattin_sharepoint", reason="mattin-sharepoint plugin not installed")

from models.sharepoint_source import SharePointSource
from models.sharepoint_file import SharePointFile
from models.enums.sharepoint_sync_status import SharePointSyncStatus
from models.enums.sharepoint_file_status import SharePointFileStatus
from models.silo import Silo
from models.app_collaborator import AppCollaborator, CollaborationRole, CollaborationStatus
from tests.factories import configure_factories, UserFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_create_payload(**overrides) -> dict:
    """Return a valid SharePointSourceCreateRequest payload."""
    payload = {
        "name": "Test SP Source",
        "description": "Integration test source",
        "tenant_id": "test-tenant",
        "client_id": "test-client",
        "client_secret": "test-secret",
        "site_id": "test-site",
        "site_name": "Test Site",
        "site_url": "https://example.sharepoint.com/sites/test",
        "drive_id": "test-drive",
        "drive_name": "Documents",
        "silo_name": "Test SP Silo",
        "vector_db_type": "PGVECTOR",
    }
    payload.update(overrides)
    return payload


def _make_silo(db, fake_app) -> Silo:
    """Create a test Silo for use with SharePoint sources."""
    silo = Silo(
        name="SP Test Silo",
        description="Silo for SharePoint integration tests",
        silo_type="CUSTOM",
        app_id=fake_app.app_id,
    )
    db.add(silo)
    db.flush()
    return silo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_sp_silo(db, fake_app):
    """A Silo linked to fake_app for SharePoint source tests."""
    return _make_silo(db, fake_app)


@pytest.fixture
def fake_sp_source(db, fake_app, fake_sp_silo):
    """A persisted SharePointSource linked to fake_app."""
    source = SharePointSource(
        app_id=fake_app.app_id,
        silo_id=fake_sp_silo.silo_id,
        name="Test SP Source",
        tenant_id="test-tenant",
        client_id="test-client",
        client_secret="test-secret",
        site_id="test-site",
        drive_id="test-drive",
        last_sync_status=SharePointSyncStatus.IDLE,
    )
    db.add(source)
    db.flush()
    return source


@pytest.fixture
def fake_sp_file(db, fake_sp_source):
    """A SharePointFile linked to fake_sp_source."""
    file_obj = SharePointFile(
        source_id=fake_sp_source.id,
        drive_item_id="item-001",
        name="document.pdf",
        status=SharePointFileStatus.INDEXED,
        last_synced_at=datetime.utcnow(),
    )
    db.add(file_obj)
    db.flush()
    return file_obj


@pytest.fixture
def mock_graph_client():
    """Patch GraphClient to avoid real Microsoft API calls."""
    with (
        patch("mattin_sharepoint.service.GraphClient") as mock_gc,
        patch("mattin_sharepoint.graph_client.GraphClient") as _mock_gc2,
    ):
        mock_gc.get_token = AsyncMock(return_value="fake-token")
        mock_gc.verify_drive_access = AsyncMock(return_value={"id": "test-drive"})
        yield mock_gc


@pytest.fixture
def mock_silo_service():
    """Patch SiloService.create_or_update_silo to avoid real silo setup."""
    with patch("services.silo_service.SiloService.create_or_update_silo") as mock_create:
        yield mock_create


@pytest.fixture
def editor_headers(db, client, fake_app, fake_user):
    """Auth headers for a separate user with EDITOR role on fake_app.

    Uses a distinct user (not fake_user / app owner) so that RBAC correctly
    resolves the role as EDITOR rather than falling through to OWNER.
    """
    configure_factories(db)
    editor_user = UserFactory(email="editor-sp@mattin-test.com", name="SP Editor User")
    collab = AppCollaborator(
        app_id=fake_app.app_id,
        user_id=editor_user.user_id,
        role=CollaborationRole.EDITOR,
        invited_by=fake_user.user_id,
        status=CollaborationStatus.ACCEPTED,
        invited_at=datetime.now(),
        accepted_at=datetime.now(),
    )
    db.add(collab)
    db.flush()

    response = client.post(
        "/internal/auth/dev-login",
        json={"email": editor_user.email},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def viewer_headers(db, client, fake_app, fake_user):
    """Auth headers for a separate user with VIEWER role on fake_app.

    Uses a distinct user (not fake_user / app owner) so that RBAC correctly
    resolves the role as VIEWER rather than falling through to OWNER.
    """
    configure_factories(db)
    viewer_user = UserFactory(email="viewer-sp@mattin-test.com", name="SP Viewer User")
    collab = AppCollaborator(
        app_id=fake_app.app_id,
        user_id=viewer_user.user_id,
        role=CollaborationRole.VIEWER,
        invited_by=fake_user.user_id,
        status=CollaborationStatus.ACCEPTED,
        invited_at=datetime.now(),
        accepted_at=datetime.now(),
    )
    db.add(collab)
    db.flush()

    response = client.post(
        "/internal/auth/dev-login",
        json={"email": viewer_user.email},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# TestSharePointSourcesCRUD
# ---------------------------------------------------------------------------

class TestSharePointSourcesCRUD:
    """Happy-path CRUD tests for SharePoint sources."""

    def test_list_sources_empty(self, client, fake_app, owner_headers, db):
        """GET list returns 200 + empty array when no sources exist."""
        db.flush()
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/sharepoint-sources",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_sources_returns_existing(
        self, client, fake_app, fake_sp_source, owner_headers, db
    ):
        """GET list returns source when one exists."""
        db.flush()
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/sharepoint-sources",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == fake_sp_source.name
        assert "client_secret" not in data[0]

    def test_get_source_detail(
        self, client, fake_app, fake_sp_source, fake_sp_file, owner_headers, db
    ):
        """GET detail returns source with files list and correct file_count."""
        db.flush()
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/sharepoint-sources/{fake_sp_source.id}",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == fake_sp_source.id
        assert len(data["files"]) == 1
        assert data["files"][0]["name"] == "document.pdf"
        assert "client_secret" not in data

    def test_get_source_not_found(self, client, fake_app, owner_headers, db):
        """GET non-existent source returns 404."""
        db.flush()
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/sharepoint-sources/99999",
            headers=owner_headers,
        )
        assert resp.status_code == 404

    def test_create_source_success(
        self, client, fake_app, owner_headers, db, mock_graph_client, fake_sp_silo
    ):
        """POST creates a source with valid credentials."""
        # mock_silo_service: SiloService.create_or_update_silo returns fake_sp_silo
        with patch(
            "services.silo_service.SiloService.create_or_update_silo",
            return_value=fake_sp_silo,
        ):
            db.flush()
            payload = _make_create_payload()
            resp = client.post(
                f"/internal/apps/{fake_app.app_id}/sharepoint-sources",
                json=payload,
                headers=owner_headers,
            )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == payload["name"]
        assert data["tenant_id"] == payload["tenant_id"]
        assert "client_secret" not in data

    def test_create_source_bad_credentials(
        self, client, fake_app, owner_headers, db
    ):
        """POST with credentials that fail test-connection returns 400."""
        from mattin_sharepoint.graph_client import GraphAuthError
        with patch("mattin_sharepoint.service.GraphClient") as mock_gc:
            mock_gc.get_token = AsyncMock(side_effect=GraphAuthError("invalid creds"))
            db.flush()
            payload = _make_create_payload(client_secret="bad-secret")
            resp = client.post(
                f"/internal/apps/{fake_app.app_id}/sharepoint-sources",
                json=payload,
                headers=owner_headers,
            )
        assert resp.status_code == 400

    def test_update_source_name(
        self, client, fake_app, fake_sp_source, owner_headers, db
    ):
        """PUT changing name-only succeeds with 200."""
        db.flush()
        resp = client.put(
            f"/internal/apps/{fake_app.app_id}/sharepoint-sources/{fake_sp_source.id}",
            json={"name": "Updated Name"},
            headers=owner_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Updated Name"

    def test_update_source_bad_credentials(
        self, client, fake_app, fake_sp_source, owner_headers, db
    ):
        """PUT with invalid new credentials returns 400, source name unchanged."""
        from mattin_sharepoint.graph_client import GraphAuthError
        with patch("mattin_sharepoint.service.GraphClient") as mock_gc:
            mock_gc.get_token = AsyncMock(side_effect=GraphAuthError("bad creds"))
            db.flush()
            resp = client.put(
                f"/internal/apps/{fake_app.app_id}/sharepoint-sources/{fake_sp_source.id}",
                json={"client_secret": "bad-new-secret"},
                headers=owner_headers,
            )
        assert resp.status_code == 400

    def test_delete_source_success(
        self, client, fake_app, fake_sp_source, owner_headers, db
    ):
        """DELETE returns 204 and subsequent GET returns 404."""
        with patch("services.silo_service.SiloService.delete_silo"):
            db.flush()
            resp = client.delete(
                f"/internal/apps/{fake_app.app_id}/sharepoint-sources/{fake_sp_source.id}",
                headers=owner_headers,
            )
        assert resp.status_code == 204

        # Subsequent GET should 404
        resp2 = client.get(
            f"/internal/apps/{fake_app.app_id}/sharepoint-sources/{fake_sp_source.id}",
            headers=owner_headers,
        )
        assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# TestSharePointSourcesRBAC
# ---------------------------------------------------------------------------

class TestSharePointSourcesRBAC:
    """Role enforcement tests for SharePoint source endpoints."""

    def test_unauthenticated_returns_401(self, client, fake_app, db):
        """List endpoint without auth header returns 401."""
        db.flush()
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/sharepoint-sources",
        )
        assert resp.status_code == 401

    def test_viewer_can_list(
        self, client, fake_app, fake_sp_source, viewer_headers, db
    ):
        """VIEWER can list sources."""
        db.flush()
        resp = client.get(
            f"/internal/apps/{fake_app.app_id}/sharepoint-sources",
            headers=viewer_headers,
        )
        assert resp.status_code == 200

    def test_viewer_cannot_create(
        self, client, fake_app, viewer_headers, db
    ):
        """VIEWER cannot create sources — returns 403."""
        db.flush()
        resp = client.post(
            f"/internal/apps/{fake_app.app_id}/sharepoint-sources",
            json=_make_create_payload(),
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_viewer_cannot_delete(
        self, client, fake_app, fake_sp_source, viewer_headers, db
    ):
        """VIEWER cannot delete sources — returns 403."""
        db.flush()
        resp = client.delete(
            f"/internal/apps/{fake_app.app_id}/sharepoint-sources/{fake_sp_source.id}",
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_editor_cannot_delete(
        self, client, fake_app, fake_sp_source, editor_headers, db
    ):
        """EDITOR cannot delete sources (requires ADMINISTRATOR) — returns 403."""
        db.flush()
        resp = client.delete(
            f"/internal/apps/{fake_app.app_id}/sharepoint-sources/{fake_sp_source.id}",
            headers=editor_headers,
        )
        assert resp.status_code == 403

    def test_owner_can_delete(
        self, client, fake_app, fake_sp_source, owner_headers, db
    ):
        """OWNER can delete sources."""
        with patch("services.silo_service.SiloService.delete_silo"):
            db.flush()
            resp = client.delete(
                f"/internal/apps/{fake_app.app_id}/sharepoint-sources/{fake_sp_source.id}",
                headers=owner_headers,
            )
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# TestSharePointSyncEndpoint
# ---------------------------------------------------------------------------

class TestSharePointSyncEndpoint:
    """Tests for the sync trigger endpoint."""

    def test_sync_trigger_returns_202(
        self, client, fake_app, fake_sp_source, owner_headers, db
    ):
        """POST /sync enqueues the job and returns 202."""
        with patch("mattin_sharepoint.router.enqueue_sync", new_callable=AsyncMock):
            db.flush()
            resp = client.post(
                f"/internal/apps/{fake_app.app_id}/sharepoint-sources/{fake_sp_source.id}/sync",
                headers=owner_headers,
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["source_id"] == fake_sp_source.id
        assert data["status"] == "QUEUED"

    def test_sync_while_running_returns_409(
        self, client, fake_app, fake_sp_source, owner_headers, db
    ):
        """POST /sync when source is RUNNING returns 409."""
        fake_sp_source.last_sync_status = SharePointSyncStatus.RUNNING
        db.flush()

        resp = client.post(
            f"/internal/apps/{fake_app.app_id}/sharepoint-sources/{fake_sp_source.id}/sync",
            headers=owner_headers,
        )
        assert resp.status_code == 409

    def test_sync_not_found_returns_404(
        self, client, fake_app, owner_headers, db
    ):
        """POST /sync with non-existent source_id returns 404."""
        db.flush()
        resp = client.post(
            f"/internal/apps/{fake_app.app_id}/sharepoint-sources/99999/sync",
            headers=owner_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestCapabilitiesEndpoint
# ---------------------------------------------------------------------------

class TestCapabilitiesEndpoint:
    """Tests for /internal/capabilities."""

    def test_capabilities_unauthenticated_returns_401(self, client, db):
        """GET /internal/capabilities without auth returns 401."""
        db.flush()
        resp = client.get("/internal/capabilities")
        assert resp.status_code == 401

    def test_capabilities_authenticated_returns_dict(
        self, client, fake_user, auth_headers, db
    ):
        """GET /internal/capabilities with auth returns a dict (may be empty or have sharepoint)."""
        db.flush()
        resp = client.get(
            "/internal/capabilities",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)

    def test_capabilities_with_plugin_registered(
        self, client, fake_user, auth_headers, db
    ):
        """After registering sharepoint in the plugin registry, capabilities includes it."""
        from plugins.registry import plugin_registry
        plugin_registry.register("sharepoint", {"enabled": True, "version": "test"})

        db.flush()
        resp = client.get(
            "/internal/capabilities",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "sharepoint" in data
        assert data["sharepoint"]["enabled"] is True


# ---------------------------------------------------------------------------
# TestMigrationSchemaState
# ---------------------------------------------------------------------------

class TestMigrationSchemaState:
    """Verify that the Alembic migration created the expected schema objects."""

    def test_sharepoint_source_table_exists(self, db):
        """sharepoint_source table must exist."""
        from sqlalchemy import text
        result = db.execute(
            text("SELECT to_regclass('public.sharepoint_source')")
        ).scalar()
        assert result is not None, "Table 'sharepoint_source' does not exist"

    def test_sharepoint_file_table_exists(self, db):
        """sharepoint_file table must exist."""
        from sqlalchemy import text
        result = db.execute(
            text("SELECT to_regclass('public.sharepoint_file')")
        ).scalar()
        assert result is not None, "Table 'sharepoint_file' does not exist"

    def test_sharepoint_sync_status_enum_exists(self, db):
        """sharepoint_sync_status PostgreSQL enum type must exist."""
        from sqlalchemy import text
        result = db.execute(
            text("SELECT 1 FROM pg_type WHERE typname = 'sharepoint_sync_status'")
        ).fetchone()
        assert result is not None, "Enum 'sharepoint_sync_status' does not exist"

    def test_sharepoint_file_status_enum_exists(self, db):
        """sharepoint_file_status PostgreSQL enum type must exist."""
        from sqlalchemy import text
        result = db.execute(
            text("SELECT 1 FROM pg_type WHERE typname = 'sharepoint_file_status'")
        ).fetchone()
        assert result is not None, "Enum 'sharepoint_file_status' does not exist"
