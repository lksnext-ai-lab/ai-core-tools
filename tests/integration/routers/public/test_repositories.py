"""
Integration tests for public API repository endpoints.

Uses the shared test infrastructure (TestClient, transactional DB, real API key).
Service-level operations that touch the filesystem or vector DB are mocked.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def repos_url(app_id: int, repo_id: int = None, suffix: str = "") -> str:
    base = f"/public/v1/app/{app_id}/repositories"
    if repo_id is not None:
        base = f"{base}/{repo_id}"
    return f"{base}{suffix}"


def api_headers(key: str) -> dict:
    return {"X-API-KEY": key}


# ---------------------------------------------------------------------------
# Fixtures (test-local, no conftest changes)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_silo(db, fake_app):
    from models.silo import Silo

    silo = Silo(
        name="Test Silo",
        description="Silo for test repository",
        status="active",
        silo_type="REPO",
        app_id=fake_app.app_id,
        vector_db_type="PGVECTOR",
    )
    db.add(silo)
    db.flush()
    return silo


@pytest.fixture
def fake_repository(db, fake_app, fake_silo):
    from models.repository import Repository

    repo = Repository(
        name="Test Repository",
        type="default",
        status="active",
        app_id=fake_app.app_id,
        silo_id=fake_silo.silo_id,
        create_date=datetime.now(),
    )
    db.add(repo)
    db.flush()
    return repo


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestRepositoryAuth:
    def test_no_api_key_returns_401(self, client, fake_app):
        resp = client.get(repos_url(fake_app.app_id))
        assert resp.status_code == 401

    def test_invalid_api_key_returns_401(self, client, fake_app):
        resp = client.get(
            repos_url(fake_app.app_id),
            headers=api_headers("totally-invalid-key"),
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# List repositories
# ---------------------------------------------------------------------------


class TestListRepositories:
    def test_returns_200_with_repos(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        resp = client.get(
            repos_url(fake_app.app_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "repositories" in data
        assert len(data["repositories"]) >= 1

        repo_data = data["repositories"][0]
        assert "repository_id" in repo_data
        assert "name" in repo_data
        assert "type" in repo_data
        assert "status" in repo_data
        # silo_id should NOT be exposed
        assert "silo_id" not in repo_data

    def test_empty_app_returns_empty_list(
        self, client, fake_app, fake_api_key, db
    ):
        """App with no repositories returns empty list."""
        from models.repository import Repository

        db.query(Repository).filter(Repository.app_id == fake_app.app_id).delete()
        db.flush()

        resp = client.get(
            repos_url(fake_app.app_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert resp.json()["repositories"] == []


# ---------------------------------------------------------------------------
# Get repository
# ---------------------------------------------------------------------------


class TestGetRepository:
    def test_returns_200_with_detail(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        resp = client.get(
            repos_url(fake_app.app_id, fake_repository.repository_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "repository" in data
        repo = data["repository"]
        assert repo["repository_id"] == fake_repository.repository_id
        assert repo["name"] == fake_repository.name
        assert "silo_id" not in repo

    def test_nonexistent_repo_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        resp = client.get(
            repos_url(fake_app.app_id, 999999),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_repo_from_other_app_returns_404(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        """Accessing a repo via a different app_id should return 404 (IDOR protection)."""
        other_app_id = fake_app.app_id + 1000
        resp = client.get(
            repos_url(other_app_id, fake_repository.repository_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code in (401, 403, 404)


# ---------------------------------------------------------------------------
# Create repository
# ---------------------------------------------------------------------------


class TestCreateRepository:
    def test_create_repo_returns_201(
        self, client, fake_app, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.RepositoryService.create_repository"
        ) as mock_create:
            from models.repository import Repository

            created = Repository(
                repository_id=9999,
                name="New Repo",
                type="default",
                status="active",
                app_id=fake_app.app_id,
                silo_id=1,
                create_date=datetime.now(),
            )
            mock_create.return_value = created

            resp = client.post(
                repos_url(fake_app.app_id),
                json={"name": "New Repo"},
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 201
            data = resp.json()
            assert "repository" in data
            assert data["repository"]["name"] == "New Repo"

    def test_missing_name_returns_422(
        self, client, fake_app, fake_api_key, db
    ):
        """Pydantic validation rejects missing required field."""
        resp = client.post(
            repos_url(fake_app.app_id),
            json={},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Update repository
# ---------------------------------------------------------------------------


class TestUpdateRepository:
    def test_update_repo_returns_200(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.RepositoryService.update_repository"
        ) as mock_update:
            fake_repository.name = "Updated Name"
            mock_update.return_value = fake_repository

            resp = client.put(
                repos_url(fake_app.app_id, fake_repository.repository_id),
                json={"name": "Updated Name"},
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 200
            assert resp.json()["repository"]["name"] == "Updated Name"

    def test_update_nonexistent_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        resp = client.put(
            repos_url(fake_app.app_id, 999999),
            json={"name": "Ghost"},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete repository
# ---------------------------------------------------------------------------


class TestDeleteRepository:
    def test_delete_repo_returns_204(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.repositories.RepositoryService.delete_repository"
        ) as mock_delete:
            mock_delete.return_value = None

            resp = client.delete(
                repos_url(fake_app.app_id, fake_repository.repository_id),
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 204

    def test_delete_nonexistent_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        resp = client.delete(
            repos_url(fake_app.app_id, 999999),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Find docs
# ---------------------------------------------------------------------------


class TestFindDocs:
    def test_find_docs_returns_200(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        mock_doc = MagicMock()
        mock_doc.page_content = "Test content"
        mock_doc.metadata = {"source": "test.pdf"}
        mock_doc.id = "doc-1"

        with patch(
            "routers.public.v1.repositories.SiloService.find_docs_in_collection",
            return_value=[mock_doc],
        ):
            resp = client.post(
                repos_url(fake_app.app_id, fake_repository.repository_id, "/docs/find"),
                json={"query": "test query"},
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "docs" in data
            assert len(data["docs"]) == 1
            assert data["docs"][0]["page_content"] == "Test content"

    def test_find_docs_repo_not_found_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        resp = client.post(
            repos_url(fake_app.app_id, 999999, "/docs/find"),
            json={"query": "test"},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_find_docs_error_does_not_leak_details(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        """Internal errors should return generic messages, not stack traces."""
        with patch(
            "routers.public.v1.repositories.SiloService.find_docs_in_collection",
            side_effect=RuntimeError("disk full /dev/sda1 connection refused pg_hba.conf"),
        ):
            resp = client.post(
                repos_url(fake_app.app_id, fake_repository.repository_id, "/docs/find"),
                json={"query": "test"},
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 500
            detail = resp.json()["detail"]
            assert "disk full" not in detail
            assert "pg_hba" not in detail
            assert "Error finding documents" in detail
