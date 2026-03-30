"""Integration tests for admin system embedding service endpoints.

Requires test DB on port 5433.
Run with: pytest tests/integration/test_admin_system_embedding_services.py -v
"""
import pytest
from datetime import datetime


# ---------------------------------------------------------------------------
# Module-level fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def admin_headers(fake_user, client, db, monkeypatch):
    """
    Auth headers for fake_user promoted to OMNIADMIN via monkeypatch.

    monkeypatch.setenv is safe here because is_omniadmin uses os.getenv at
    call time (not module-level), so patching before the request is sufficient.
    """
    monkeypatch.setenv("AICT_OMNIADMINS", fake_user.email)
    db.flush()
    response = client.post(
        "/internal/auth/dev-login",
        json={"email": fake_user.email},
    )
    assert response.status_code == 200, (
        f"Admin login failed ({response.status_code}): {response.text}"
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def system_embedding_svc(db):
    """A system EmbeddingService (app_id=None) for use in tests."""
    from models.embedding_service import EmbeddingService

    svc = EmbeddingService(
        name="Platform OpenAI Embeddings",
        provider="OpenAI",
        api_key="sk-sys",  # pragma: allowlist secret
        description="text-embedding-3-small",
        endpoint="",
        app_id=None,
        create_date=datetime.now(),
    )
    db.add(svc)
    db.flush()
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSystemEmbeddingServiceAdmin:

    def test_list_system_embedding_services_requires_admin(self, auth_headers, client):
        """Non-admin users receive 403 from the admin endpoint."""
        # auth_headers is a regular user (not omniadmin) — re-use the fixture
        # but get headers WITHOUT monkeypatching AICT_OMNIADMINS.
        # We call the endpoint with the regular auth_headers fixture.
        response = client.get(
            "/internal/admin/system-embedding-services",
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_create_system_embedding_service(self, admin_headers, client):
        """Admin can create a system embedding service; response has is_system=True."""
        payload = {
            "name": "New System Embeddings",
            "provider": "OpenAI",
            "model_name": "text-embedding-3-large",
            "api_key": "sk-newsys",  # pragma: allowlist secret
            "base_url": "",
        }
        response = client.post(
            "/internal/admin/system-embedding-services",
            json=payload,
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert "service_id" in data
        assert data["is_system"] is True
        assert data["name"] == "New System Embeddings"

    def test_update_system_embedding_service(
        self, admin_headers, client, system_embedding_svc
    ):
        """Admin can update a system embedding service name."""
        payload = {
            "name": "Updated Platform Embeddings",
            "provider": "OpenAI",
            "model_name": "text-embedding-3-small",
            "api_key": "sk-sys",  # pragma: allowlist secret
            "base_url": "",
        }
        response = client.put(
            f"/internal/admin/system-embedding-services/{system_embedding_svc.service_id}",
            json=payload,
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["name"] == "Updated Platform Embeddings"

    def test_update_app_scoped_service_via_admin_returns_404(
        self, admin_headers, client, db, fake_app
    ):
        """Attempting to update an app-scoped service via admin endpoint returns 404."""
        from models.embedding_service import EmbeddingService

        app_svc = EmbeddingService(
            name="App Embeddings",
            provider="OpenAI",
            api_key="sk-app",  # pragma: allowlist secret
            description="text-embedding-ada-002",
            endpoint="",
            app_id=fake_app.app_id,
            create_date=datetime.now(),
        )
        db.add(app_svc)
        db.flush()

        payload = {
            "name": "Attempted Update",
            "provider": "OpenAI",
            "model_name": "text-embedding-ada-002",
            "api_key": "sk-app",  # pragma: allowlist secret
            "base_url": "",
        }
        response = client.put(
            f"/internal/admin/system-embedding-services/{app_svc.service_id}",
            json=payload,
            headers=admin_headers,
        )
        assert response.status_code == 404

    def test_delete_system_embedding_service_no_silos(
        self, admin_headers, client, system_embedding_svc, db
    ):
        """Admin can delete a system embedding service with no silos referencing it."""
        from repositories.embedding_service_repository import EmbeddingServiceRepository

        service_id = system_embedding_svc.service_id
        response = client.delete(
            f"/internal/admin/system-embedding-services/{service_id}",
            headers=admin_headers,
        )
        assert response.status_code == 204

        # Verify deleted
        db.expire_all()
        remaining = EmbeddingServiceRepository.get_by_id(db, service_id)
        assert remaining is None

    def test_delete_system_embedding_service_with_silos_nullifies_references(
        self, admin_headers, client, system_embedding_svc, db, fake_app
    ):
        """Deleting a system service sets embedding_service_id to NULL on referencing silos."""
        from models.silo import Silo

        silo = Silo(
            name="Test Silo",
            app_id=fake_app.app_id,
            embedding_service_id=system_embedding_svc.service_id,
            create_date=datetime.now(),
        )
        db.add(silo)
        db.flush()
        silo_id = silo.silo_id

        response = client.delete(
            f"/internal/admin/system-embedding-services/{system_embedding_svc.service_id}",
            headers=admin_headers,
        )
        assert response.status_code == 204

        db.expire_all()
        refreshed_silo = db.query(Silo).filter(Silo.silo_id == silo_id).first()
        assert refreshed_silo is not None
        assert refreshed_silo.embedding_service_id is None

    def test_impact_endpoint_returns_correct_counts(
        self, admin_headers, client, system_embedding_svc, db, fake_app
    ):
        """Impact endpoint counts silos and apps correctly."""
        from models.silo import Silo

        silo = Silo(
            name="Impact Test Silo",
            app_id=fake_app.app_id,
            embedding_service_id=system_embedding_svc.service_id,
            create_date=datetime.now(),
        )
        db.add(silo)
        db.flush()

        response = client.get(
            f"/internal/admin/system-embedding-services/{system_embedding_svc.service_id}/impact",
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["affected_silos_count"] == 1
        assert data["affected_apps_count"] == 1
        assert data["affected_silos"][0]["silo_name"] == "Impact Test Silo"

    def test_silo_form_includes_system_embedding_services(
        self, owner_headers, client, system_embedding_svc, db, fake_app
    ):
        """Silo detail response includes both app-scoped and system embedding services."""
        from models.embedding_service import EmbeddingService
        from models.silo import Silo

        # App-scoped embedding service
        app_svc = EmbeddingService(
            name="App Embeddings",
            provider="OpenAI",
            api_key="sk-app",  # pragma: allowlist secret
            description="text-embedding-ada-002",
            endpoint="",
            app_id=fake_app.app_id,
            create_date=datetime.now(),
        )
        db.add(app_svc)

        # A real silo to get detail for
        silo = Silo(
            name="Detail Test Silo",
            app_id=fake_app.app_id,
            embedding_service_id=app_svc.service_id,
            create_date=datetime.now(),
        )
        db.add(silo)
        db.flush()

        response = client.get(
            f"/internal/apps/{fake_app.app_id}/silos/{silo.silo_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()

        embedding_services = data["embedding_services"]
        service_ids = [s["service_id"] for s in embedding_services]
        assert app_svc.service_id in service_ids
        assert system_embedding_svc.service_id in service_ids

        # Verify is_system flags
        sys_entry = next(s for s in embedding_services if s["service_id"] == system_embedding_svc.service_id)
        app_entry = next(s for s in embedding_services if s["service_id"] == app_svc.service_id)
        assert sys_entry["is_system"] is True
        assert app_entry["is_system"] is False
