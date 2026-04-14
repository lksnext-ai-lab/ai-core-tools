"""
Integration tests for silo tenant isolation in the public API.

Ensures that document-operation endpoints under /public/v1/app/{app_id}/silos/{silo_id}/docs/
reject requests where the silo does not belong to the authenticated app.

Endpoints under test:
  GET    /public/v1/app/{app_id}/silos/{silo_id}/docs
  POST   /public/v1/app/{app_id}/silos/{silo_id}/docs/index
  POST   /public/v1/app/{app_id}/silos/{silo_id}/docs/multiple-index
  DELETE /public/v1/app/{app_id}/silos/{silo_id}/docs/delete
  DELETE /public/v1/app/{app_id}/silos/{silo_id}/docs/delete-by-metadata
  DELETE /public/v1/app/{app_id}/silos/{silo_id}/docs/delete/all
  POST   /public/v1/app/{app_id}/silos/{silo_id}/docs/find
  POST   /public/v1/app/{app_id}/silos/{silo_id}/docs/index-file

Security requirement: each endpoint must return 404 when the silo belongs to a
different app than the one associated with the API key (no information disclosure),
and 404 when the silo does not exist.
"""

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_key_headers(key: str) -> dict:
    return {"X-API-KEY": key}


def docs_url(app_id: int, silo_id: int, suffix: str = "") -> str:
    base = f"/public/v1/app/{app_id}/silos/{silo_id}/docs"
    if suffix:
        return f"{base}/{suffix}"
    return base


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
# Cross-tenant access tests (expect 404 — IDOR protection)
# ---------------------------------------------------------------------------


class TestSiloTenantIsolation:
    """
    Use fake_app's API key (fake_api_key) against a silo owned by other_app.
    All document endpoints must return 404 (not 403, to avoid confirming existence).
    """

    def test_count_docs_cross_tenant_returns_404(
        self, client, fake_app, fake_api_key, other_silo
    ):
        resp = client.get(
            docs_url(fake_app.app_id, other_silo.silo_id),
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_index_single_doc_cross_tenant_returns_404(
        self, client, fake_app, fake_api_key, other_silo
    ):
        resp = client.post(
            docs_url(fake_app.app_id, other_silo.silo_id, "index"),
            json={"content": "Hello world", "metadata": {}},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_index_multiple_docs_cross_tenant_returns_404(
        self, client, fake_app, fake_api_key, other_silo
    ):
        resp = client.post(
            docs_url(fake_app.app_id, other_silo.silo_id, "multiple-index"),
            json={"documents": [{"content": "doc1", "metadata": {}}]},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_delete_docs_cross_tenant_returns_404(
        self, client, fake_app, fake_api_key, other_silo
    ):
        resp = client.request(
            "DELETE",
            docs_url(fake_app.app_id, other_silo.silo_id, "delete"),
            json={"ids": ["some-id"]},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_delete_docs_by_metadata_cross_tenant_returns_404(
        self, client, fake_app, fake_api_key, other_silo
    ):
        resp = client.request(
            "DELETE",
            docs_url(fake_app.app_id, other_silo.silo_id, "delete-by-metadata"),
            json={"filter_metadata": {"resource_id": {"$eq": "123"}}},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_delete_all_docs_cross_tenant_returns_404(
        self, client, fake_app, fake_api_key, other_silo
    ):
        resp = client.delete(
            docs_url(fake_app.app_id, other_silo.silo_id, "delete/all"),
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_find_docs_cross_tenant_returns_404(
        self, client, fake_app, fake_api_key, other_silo
    ):
        resp = client.post(
            docs_url(fake_app.app_id, other_silo.silo_id, "find"),
            json={"query": "test"},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_index_file_cross_tenant_returns_404(
        self, client, fake_app, fake_api_key, other_silo
    ):
        file_content = b"Hello, world!"
        resp = client.post(
            docs_url(fake_app.app_id, other_silo.silo_id, "index-file"),
            files={"file": ("test.txt", file_content, "text/plain")},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404


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
        resp = client.get(
            docs_url(fake_app.app_id, self.NON_EXISTENT_SILO_ID),
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_index_single_doc_missing_silo_returns_404(
        self, client, fake_app, fake_api_key
    ):
        resp = client.post(
            docs_url(fake_app.app_id, self.NON_EXISTENT_SILO_ID, "index"),
            json={"content": "Hello", "metadata": {}},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_delete_all_docs_missing_silo_returns_404(
        self, client, fake_app, fake_api_key
    ):
        resp = client.delete(
            docs_url(fake_app.app_id, self.NON_EXISTENT_SILO_ID, "delete/all"),
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_find_docs_missing_silo_returns_404(
        self, client, fake_app, fake_api_key
    ):
        resp = client.post(
            docs_url(fake_app.app_id, self.NON_EXISTENT_SILO_ID, "find"),
            json={"query": "test"},
            headers=api_key_headers(fake_api_key.key),
        )
        assert resp.status_code == 404
