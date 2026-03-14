"""
Integration tests for public API silos endpoints.

Uses the shared test infrastructure (TestClient, transactional DB, real API key).
Only vector DB / service operations are mocked — auth, routing, Pydantic, and DB are real.
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def silos_url(app_id: int, silo_id: int = None, suffix: str = None) -> str:
    base = f"/public/v1/app/{app_id}/silos"
    if silo_id is not None:
        base = f"{base}/{silo_id}"
    if suffix:
        base = f"{base}/{suffix}"
    return base


def api_headers(key: str) -> dict:
    return {"X-API-KEY": key}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_silo(db, fake_app):
    """A CUSTOM silo belonging to fake_app."""
    from models.silo import Silo

    silo = Silo(
        name="Test Silo",
        description="Silo for integration tests",
        app_id=fake_app.app_id,
        silo_type="CUSTOM",
        status="active",
        vector_db_type="PGVECTOR",
    )
    db.add(silo)
    db.flush()
    return silo


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestSiloAuth:
    def test_no_api_key_returns_401(self, client, fake_app):
        resp = client.get(silos_url(fake_app.app_id))
        assert resp.status_code == 401

    def test_invalid_api_key_returns_401(self, client, fake_app):
        resp = client.get(
            silos_url(fake_app.app_id),
            headers=api_headers("totally-invalid-key"),
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# List silos
# ---------------------------------------------------------------------------


class TestListSilos:
    def test_returns_200_with_silos(
        self, client, fake_app, fake_silo, fake_api_key, db
    ):
        resp = client.get(
            silos_url(fake_app.app_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "silos" in data
        assert len(data["silos"]) >= 1

        silo_data = data["silos"][0]
        assert "silo_id" in silo_data
        assert "name" in silo_data
        assert "docs_count" in silo_data

    def test_empty_app_returns_empty_list(
        self, client, fake_app, fake_api_key, db
    ):
        """App with no silos returns empty list."""
        from models.silo import Silo

        db.query(Silo).filter(Silo.app_id == fake_app.app_id).delete()
        db.flush()

        resp = client.get(
            silos_url(fake_app.app_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert resp.json()["silos"] == []


# ---------------------------------------------------------------------------
# Get silo
# ---------------------------------------------------------------------------


class TestGetSilo:
    def test_returns_200_with_detail(
        self, client, fake_app, fake_silo, fake_api_key, db
    ):
        resp = client.get(
            silos_url(fake_app.app_id, fake_silo.silo_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "silo" in data
        silo = data["silo"]
        assert silo["silo_id"] == fake_silo.silo_id
        assert silo["name"] == fake_silo.name

    def test_nonexistent_silo_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        resp = client.get(
            silos_url(fake_app.app_id, 999999),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_silo_from_other_app_returns_404(
        self, client, fake_app, fake_silo, fake_api_key, db
    ):
        """Accessing a silo via a different app_id should return 404 (IDOR protection)."""
        other_app_id = fake_app.app_id + 1000
        resp = client.get(
            silos_url(other_app_id, fake_silo.silo_id),
            headers=api_headers(fake_api_key.key),
        )
        # Either 404 (silo not in app) or 401/403 (key not valid for other app)
        assert resp.status_code in (401, 403, 404)

    def test_no_internal_fields_exposed(
        self, client, fake_app, fake_silo, fake_api_key, db
    ):
        """Public schema should not expose internal form data."""
        resp = client.get(
            silos_url(fake_app.app_id, fake_silo.silo_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        silo = resp.json()["silo"]
        # These internal fields should NOT be in the public response
        assert "output_parsers" not in silo
        assert "embedding_services" not in silo
        assert "vector_db_options" not in silo
        assert "metadata_fields" not in silo


# ---------------------------------------------------------------------------
# Create silo
# ---------------------------------------------------------------------------


class TestCreateSilo:
    def test_create_silo_returns_201(
        self, client, fake_app, fake_api_key, db
    ):
        payload = {
            "name": "Integration Test Silo",
            "description": "Created by integration test",
            "type": "CUSTOM",
        }
        resp = client.post(
            silos_url(fake_app.app_id),
            json=payload,
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "silo" in data
        assert data["silo"]["name"] == "Integration Test Silo"
        assert data["silo"]["silo_id"] is not None

    def test_missing_name_returns_422(
        self, client, fake_app, fake_api_key, db
    ):
        """Pydantic validation rejects missing required field."""
        payload = {"description": "No name provided"}
        resp = client.post(
            silos_url(fake_app.app_id),
            json=payload,
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Update silo
# ---------------------------------------------------------------------------


class TestUpdateSilo:
    def test_update_silo_returns_200(
        self, client, fake_app, fake_silo, fake_api_key, db
    ):
        payload = {"name": "Updated Silo Name", "description": "Updated description"}
        resp = client.put(
            silos_url(fake_app.app_id, fake_silo.silo_id),
            json=payload,
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert resp.json()["silo"]["name"] == "Updated Silo Name"

    def test_update_nonexistent_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        payload = {"name": "Ghost"}
        resp = client.put(
            silos_url(fake_app.app_id, 999999),
            json=payload,
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete silo
# ---------------------------------------------------------------------------


class TestDeleteSilo:
    def test_delete_silo_returns_204(
        self, client, fake_app, fake_silo, fake_api_key, db
    ):
        resp = client.delete(
            silos_url(fake_app.app_id, fake_silo.silo_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 204

    def test_delete_nonexistent_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        resp = client.delete(
            silos_url(fake_app.app_id, 999999),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Search silo
# ---------------------------------------------------------------------------


class TestSearchSilo:
    @patch("routers.public.v1.silos.SiloService.search_silo_documents_router")
    def test_search_returns_200(
        self, mock_search, client, fake_app, fake_silo, fake_api_key, db
    ):
        mock_search.return_value = {
            "query": "test query",
            "results": [
                {
                    "page_content": "Test content",
                    "metadata": {"source": "test"},
                    "score": 0.95,
                }
            ],
            "total_results": 1,
        }

        resp = client.post(
            silos_url(fake_app.app_id, fake_silo.silo_id, "search"),
            json={"query": "test query"},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test query"
        assert data["total_results"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["page_content"] == "Test content"

    def test_search_nonexistent_silo_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        resp = client.post(
            silos_url(fake_app.app_id, 999999, "search"),
            json={"query": "test"},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Document operations
# ---------------------------------------------------------------------------


class TestDocOperations:
    @patch("routers.public.v1.silos.SiloService.count_docs_in_silo")
    def test_count_docs(
        self, mock_count, client, fake_app, fake_silo, fake_api_key, db
    ):
        mock_count.return_value = 42

        resp = client.get(
            silos_url(fake_app.app_id, fake_silo.silo_id, "docs"),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 42

    @patch("routers.public.v1.silos.SiloService.index_single_content")
    def test_index_single_doc(
        self, mock_index, client, fake_app, fake_silo, fake_api_key, db
    ):
        mock_index.return_value = None

        resp = client.post(
            silos_url(fake_app.app_id, fake_silo.silo_id, "docs/index"),
            json={"content": "Hello world", "metadata": {"source": "test"}},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert "indexed" in resp.json()["message"].lower()

    @patch("routers.public.v1.silos.SiloService.index_multiple_content")
    def test_index_multiple_docs(
        self, mock_index, client, fake_app, fake_silo, fake_api_key, db
    ):
        mock_index.return_value = None

        resp = client.post(
            silos_url(fake_app.app_id, fake_silo.silo_id, "docs/multiple-index"),
            json={
                "documents": [
                    {"content": "doc1", "metadata": {}},
                    {"content": "doc2", "metadata": {}},
                ]
            },
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert "2" in resp.json()["message"]

    @patch("routers.public.v1.silos.SiloService.find_docs_in_collection")
    def test_find_docs(
        self, mock_find, client, fake_app, fake_silo, fake_api_key, db
    ):
        mock_doc = MagicMock()
        mock_doc.page_content = "Found content"
        mock_doc.metadata = {"source": "test"}
        mock_find.return_value = [mock_doc]

        resp = client.post(
            silos_url(fake_app.app_id, fake_silo.silo_id, "docs/find"),
            json={"query": "test search"},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert len(resp.json()["docs"]) == 1
        assert resp.json()["docs"][0]["page_content"] == "Found content"

    @patch("routers.public.v1.silos.SiloService.delete_docs_in_collection")
    def test_delete_docs(
        self, mock_delete, client, fake_app, fake_silo, fake_api_key, db
    ):
        mock_delete.return_value = None

        resp = client.request(
            "DELETE",
            silos_url(fake_app.app_id, fake_silo.silo_id, "docs/delete"),
            json={"ids": ["id-1", "id-2"]},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert "2" in resp.json()["message"]

    @patch("routers.public.v1.silos.SiloService.delete_docs_by_metadata")
    def test_delete_by_metadata(
        self, mock_delete, client, fake_app, fake_silo, fake_api_key, db
    ):
        mock_delete.return_value = 5

        resp = client.request(
            "DELETE",
            silos_url(fake_app.app_id, fake_silo.silo_id, "docs/delete-by-metadata"),
            json={"filter_metadata": {"resource_id": {"$eq": "123"}}},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert "5" in resp.json()["message"]

    @patch("routers.public.v1.silos.SiloService.delete_all_docs_in_collection")
    def test_delete_all_docs(
        self, mock_delete, client, fake_app, fake_silo, fake_api_key, db
    ):
        mock_delete.return_value = None

        resp = client.delete(
            silos_url(fake_app.app_id, fake_silo.silo_id, "docs/delete/all"),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    def test_delete_by_metadata_empty_filter_returns_400(
        self, client, fake_app, fake_silo, fake_api_key, db
    ):
        resp = client.request(
            "DELETE",
            silos_url(fake_app.app_id, fake_silo.silo_id, "docs/delete-by-metadata"),
            json={"filter_metadata": {}},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 400

    @patch("routers.public.v1.silos.SiloService.index_multiple_content")
    @patch("routers.public.v1.silos.SiloService.extract_documents_from_file")
    def test_index_file(
        self, mock_extract, mock_index, client, fake_app, fake_silo, fake_api_key, db
    ):
        mock_doc = MagicMock()
        mock_doc.page_content = "Extracted content"
        mock_doc.metadata = {"page": 1}
        mock_extract.return_value = [mock_doc]
        mock_index.return_value = None

        resp = client.post(
            silos_url(fake_app.app_id, fake_silo.silo_id, "docs/index-file"),
            files={"file": ("test.txt", b"Hello, world!", "text/plain")},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["num_documents"] == 1
        assert "indexed" in data["message"].lower()


# ---------------------------------------------------------------------------
# Error leakage
# ---------------------------------------------------------------------------


class TestErrorLeakage:
    @patch("routers.public.v1.silos.SiloService.count_docs_in_silo")
    def test_error_does_not_expose_internals(
        self, mock_count, client, fake_app, fake_silo, fake_api_key, db
    ):
        """Service exceptions should not leak internal details in the response."""
        mock_count.side_effect = Exception(
            "FATAL: disk full on /dev/sda1, connection pool exhausted at 10.0.0.5:5432"
        )

        resp = client.get(
            silos_url(fake_app.app_id, fake_silo.silo_id, "docs"),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        # The response should NOT contain internal details
        assert "/dev/sda1" not in detail
        assert "10.0.0.5" not in detail
        assert "pool" not in detail
        assert "FATAL" not in detail

    @patch("routers.public.v1.silos.SiloService.search_silo_documents_router")
    def test_search_error_does_not_expose_internals(
        self, mock_search, client, fake_app, fake_silo, fake_api_key, db
    ):
        mock_search.side_effect = Exception(
            "psycopg2.OperationalError: FATAL password authentication failed for user 'admin'"
        )

        resp = client.post(
            silos_url(fake_app.app_id, fake_silo.silo_id, "search"),
            json={"query": "test"},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "psycopg2" not in detail
        assert "password" not in detail
        assert "admin" not in detail
