"""
Integration tests for silo tenant isolation in the public API.

Ensures that document-operation endpoints under /public/v1/silos/{silo_id}/docs/
reject requests where the silo does not belong to the authenticated app.

Endpoints under test:
  GET    /public/v1/silos/{silo_id}/docs
  POST   /public/v1/silos/{silo_id}/docs/index
  POST   /public/v1/silos/{silo_id}/docs/multiple-index
  DELETE /public/v1/silos/{silo_id}/docs/delete
  DELETE /public/v1/silos/{silo_id}/docs/delete-by-metadata
  DELETE /public/v1/silos/{silo_id}/docs/delete/all
  POST   /public/v1/silos/{silo_id}/docs/find
  POST   /public/v1/silos/{silo_id}/docs/index-file

Security requirement: each endpoint must return 403 when the silo belongs to a
different app than the one associated with the API key, and 404 when the silo
does not exist.
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_key_headers(key: str) -> dict:
    return {"X-API-KEY": key}


def _make_fake_silo(silo_id: int, app_id: int):
    """Return a minimal mock Silo ORM-like object."""
    silo = MagicMock()
    silo.silo_id = silo_id
    silo.app_id = app_id
    return silo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def other_app(db, fake_user):
    """A second App owned by the same user — simulates a different tenant."""
    from models.app import App

    app_obj = App(
        name="Other Workspace",
        slug="other-workspace-isolation-test",
        owner_id=fake_user.user_id,
        agent_rate_limit=0,
        max_file_size_mb=10,
    )
    db.add(app_obj)
    db.flush()
    return app_obj


@pytest.fixture()
def other_silo(db, other_app):
    """A Silo that belongs to *other_app*, not to fake_app."""
    from models.silo import Silo

    silo = Silo(
        name="Other Silo",
        description="Silo in another app",
        app_id=other_app.app_id,
        silo_type="CUSTOM",
        status="active",
        vector_db_type="PGVECTOR",
    )
    db.add(silo)
    db.flush()
    return silo


# ---------------------------------------------------------------------------
# Cross-tenant access tests (expect 403)
# ---------------------------------------------------------------------------


class TestSiloTenantIsolation:
    """
    Use fake_app's API key (fake_api_key) against a silo owned by other_app.
    All document endpoints must return 403.
    """

    def test_count_docs_cross_tenant_returns_403(
        self, client, fake_app, fake_api_key, other_silo
    ):
        url = f"/public/v1/silos/{other_silo.silo_id}/docs"
        resp = client.get(
            url,
            params={"app_id": fake_app.app_id},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 403

    def test_index_single_doc_cross_tenant_returns_403(
        self, client, fake_app, fake_api_key, other_silo
    ):
        url = f"/public/v1/silos/{other_silo.silo_id}/docs/index"
        resp = client.post(
            url,
            params={"app_id": fake_app.app_id},
            json={"content": "Hello world", "metadata": {}},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 403

    def test_index_multiple_docs_cross_tenant_returns_403(
        self, client, fake_app, fake_api_key, other_silo
    ):
        url = f"/public/v1/silos/{other_silo.silo_id}/docs/multiple-index"
        resp = client.post(
            url,
            params={"app_id": fake_app.app_id},
            json={"documents": [{"content": "doc1", "metadata": {}}]},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 403

    def test_delete_docs_cross_tenant_returns_403(
        self, client, fake_app, fake_api_key, other_silo
    ):
        url = f"/public/v1/silos/{other_silo.silo_id}/docs/delete"
        resp = client.delete(
            url,
            params={"app_id": fake_app.app_id},
            json={"ids": ["some-id"]},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 403

    def test_delete_docs_by_metadata_cross_tenant_returns_403(
        self, client, fake_app, fake_api_key, other_silo
    ):
        url = f"/public/v1/silos/{other_silo.silo_id}/docs/delete-by-metadata"
        resp = client.delete(
            url,
            params={"app_id": fake_app.app_id},
            json={"filter_metadata": {"resource_id": {"$eq": "123"}}},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 403

    def test_delete_all_docs_cross_tenant_returns_403(
        self, client, fake_app, fake_api_key, other_silo
    ):
        url = f"/public/v1/silos/{other_silo.silo_id}/docs/delete/all"
        resp = client.delete(
            url,
            params={"app_id": fake_app.app_id},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 403

    def test_find_docs_cross_tenant_returns_403(
        self, client, fake_app, fake_api_key, other_silo
    ):
        url = f"/public/v1/silos/{other_silo.silo_id}/docs/find"
        resp = client.post(
            url,
            params={"app_id": fake_app.app_id},
            json={"query": "test"},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 403

    def test_index_file_cross_tenant_returns_403(
        self, client, fake_app, fake_api_key, other_silo
    ):
        url = f"/public/v1/silos/{other_silo.silo_id}/docs/index-file"
        file_content = b"Hello, world!"
        resp = client.post(
            url,
            params={"app_id": fake_app.app_id},
            files={"file": ("test.txt", file_content, "text/plain")},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Non-existent silo tests (expect 404)
# ---------------------------------------------------------------------------


class TestSiloNotFound:
    """
    Requests referencing a silo that does not exist must return 404.
    """

    NON_EXISTENT_SILO_ID = 999999

    def test_count_docs_missing_silo_returns_404(
        self, client, fake_app, fake_api_key
    ):
        url = f"/public/v1/silos/{self.NON_EXISTENT_SILO_ID}/docs"
        resp = client.get(
            url,
            params={"app_id": fake_app.app_id},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_index_single_doc_missing_silo_returns_404(
        self, client, fake_app, fake_api_key
    ):
        url = f"/public/v1/silos/{self.NON_EXISTENT_SILO_ID}/docs/index"
        resp = client.post(
            url,
            params={"app_id": fake_app.app_id},
            json={"content": "Hello", "metadata": {}},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_delete_all_docs_missing_silo_returns_404(
        self, client, fake_app, fake_api_key
    ):
        url = f"/public/v1/silos/{self.NON_EXISTENT_SILO_ID}/docs/delete/all"
        resp = client.delete(
            url,
            params={"app_id": fake_app.app_id},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_find_docs_missing_silo_returns_404(
        self, client, fake_app, fake_api_key
    ):
        url = f"/public/v1/silos/{self.NON_EXISTENT_SILO_ID}/docs/find"
        resp = client.post(
            url,
            params={"app_id": fake_app.app_id},
            json={"query": "test"},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404
