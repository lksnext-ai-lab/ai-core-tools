"""
Integration tests for public API resource endpoints.

Uses the shared test infrastructure (TestClient, transactional DB, real API key).
Service-level operations that touch the filesystem or vector DB are mocked.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resources_url(app_id: int, repo_id: int, suffix: str = "") -> str:
    base = f"/public/v1/app/{app_id}/resources/{repo_id}"
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


@pytest.fixture
def fake_resource(db, fake_repository):
    from models.resource import Resource

    resource = Resource(
        name="test_document.pdf",
        uri="test_document.pdf",
        type=".pdf",
        status="active",
        repository_id=fake_repository.repository_id,
        create_date=datetime.now(),
    )
    db.add(resource)
    db.flush()
    return resource


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestResourceAuth:
    def test_no_api_key_returns_401(self, client, fake_app, fake_repository):
        resp = client.get(resources_url(fake_app.app_id, fake_repository.repository_id))
        assert resp.status_code == 401

    def test_invalid_api_key_returns_401(self, client, fake_app, fake_repository):
        resp = client.get(
            resources_url(fake_app.app_id, fake_repository.repository_id),
            headers=api_headers("totally-invalid-key"),
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# List resources
# ---------------------------------------------------------------------------


class TestListResources:
    def test_returns_200_with_resources(
        self, client, fake_app, fake_repository, fake_resource, fake_api_key, db
    ):
        resp = client.get(
            resources_url(fake_app.app_id, fake_repository.repository_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "resources" in data
        assert len(data["resources"]) >= 1

        resource_data = data["resources"][0]
        assert "resource_id" in resource_data
        assert "name" in resource_data
        assert "uri" in resource_data
        assert "type" in resource_data
        assert "repository_id" in resource_data
        # size, content_type should NOT be exposed (not in model)
        assert "size" not in resource_data
        assert "content_type" not in resource_data

    def test_empty_repo_returns_empty_list(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        """Repository with no resources returns empty list."""
        resp = client.get(
            resources_url(fake_app.app_id, fake_repository.repository_id),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 200
        assert resp.json()["resources"] == []

    def test_nonexistent_repo_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        resp = client.get(
            resources_url(fake_app.app_id, 999999),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Create resources (upload)
# ---------------------------------------------------------------------------


class TestCreateResources:
    def test_upload_returns_201(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.resources.ResourceService.upload_resources_to_repository"
        ) as mock_upload:
            mock_upload.return_value = {
                "message": "Successfully uploaded 1 files",
                "created_resources": [
                    {
                        "resource_id": 1,
                        "uri": "test.pdf",
                        "repository_id": fake_repository.repository_id,
                        "create_date": datetime.now().isoformat(),
                        "size": None,
                        "content_type": ".pdf",
                    }
                ],
                "failed_files": [],
            }

            import io

            fake_file = io.BytesIO(b"fake pdf content")
            resp = client.post(
                resources_url(fake_app.app_id, fake_repository.repository_id),
                files={"files": ("test.pdf", fake_file, "application/pdf")},
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 201
            data = resp.json()
            assert "created_resources" in data
            assert len(data["created_resources"]) == 1

    def test_upload_to_nonexistent_repo_returns_404(
        self, client, fake_app, fake_api_key, db
    ):
        """IDOR protection: cannot upload to a repo that doesn't belong to the app."""
        import io

        fake_file = io.BytesIO(b"fake content")
        resp = client.post(
            resources_url(fake_app.app_id, 999999),
            files={"files": ("test.pdf", fake_file, "application/pdf")},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_upload_idor_cross_app_returns_error(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        """Uploading to a repo via a different app_id should fail."""
        import io

        other_app_id = fake_app.app_id + 1000
        fake_file = io.BytesIO(b"fake content")
        resp = client.post(
            resources_url(other_app_id, fake_repository.repository_id),
            files={"files": ("test.pdf", fake_file, "application/pdf")},
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code in (401, 403, 404)


# ---------------------------------------------------------------------------
# Delete resource
# ---------------------------------------------------------------------------


class TestDeleteResource:
    def test_delete_returns_200(
        self, client, fake_app, fake_repository, fake_resource, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.resources.ResourceService.delete_resource_from_repository"
        ) as mock_delete:
            mock_delete.return_value = {"message": "Resource deleted"}

            resp = client.delete(
                resources_url(
                    fake_app.app_id,
                    fake_repository.repository_id,
                    f"/{fake_resource.resource_id}",
                ),
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 200
            assert "deleted" in resp.json()["message"].lower()

    def test_delete_nonexistent_returns_404(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        resp = client.delete(
            resources_url(fake_app.app_id, fake_repository.repository_id, "/999999"),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404

    def test_delete_idor_cross_repo_returns_404(
        self, client, fake_app, fake_repository, fake_resource, fake_api_key, db
    ):
        """Deleting a resource via wrong repo_id should return 404."""
        # Create another repo in the same app
        from models.repository import Repository
        from models.silo import Silo

        silo2 = Silo(
            name="Other Silo",
            description="Other",
            status="active",
            silo_type="REPO",
            app_id=fake_app.app_id,
            vector_db_type="PGVECTOR",
        )
        db.add(silo2)
        db.flush()

        other_repo = Repository(
            name="Other Repo",
            type="default",
            status="active",
            app_id=fake_app.app_id,
            silo_id=silo2.silo_id,
            create_date=datetime.now(),
        )
        db.add(other_repo)
        db.flush()

        # Try deleting fake_resource via other_repo — should fail
        resp = client.delete(
            resources_url(
                fake_app.app_id,
                other_repo.repository_id,
                f"/{fake_resource.resource_id}",
            ),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Download resource
# ---------------------------------------------------------------------------


class TestDownloadResource:
    def test_download_returns_200(
        self, client, fake_app, fake_repository, fake_resource, fake_api_key, db, tmp_path
    ):
        # Create a temporary file to serve
        test_file = tmp_path / "test_document.pdf"
        test_file.write_bytes(b"%PDF-1.4 fake content")

        with patch(
            "routers.public.v1.resources.ResourceService.download_resource_from_repository",
            return_value=(str(test_file), "test_document.pdf"),
        ):
            resp = client.get(
                resources_url(
                    fake_app.app_id,
                    fake_repository.repository_id,
                    f"/{fake_resource.resource_id}/download",
                ),
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 200

    def test_download_nonexistent_returns_404(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        resp = client.get(
            resources_url(
                fake_app.app_id,
                fake_repository.repository_id,
                "/999999/download",
            ),
            headers=api_headers(fake_api_key.key),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Error leakage
# ---------------------------------------------------------------------------


class TestErrorLeakage:
    def test_upload_error_does_not_leak_details(
        self, client, fake_app, fake_repository, fake_api_key, db
    ):
        """Internal errors should return generic messages, not stack traces."""
        with patch(
            "routers.public.v1.resources.ResourceService.upload_resources_to_repository",
            side_effect=RuntimeError("disk full /dev/sda1 connection refused pg_hba.conf"),
        ):
            import io

            fake_file = io.BytesIO(b"content")
            resp = client.post(
                resources_url(fake_app.app_id, fake_repository.repository_id),
                files={"files": ("test.pdf", fake_file, "application/pdf")},
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 500
            detail = resp.json()["detail"]
            assert "disk full" not in detail
            assert "pg_hba" not in detail

    def test_delete_error_does_not_leak_details(
        self, client, fake_app, fake_repository, fake_resource, fake_api_key, db
    ):
        with patch(
            "routers.public.v1.resources.ResourceService.delete_resource_from_repository",
            side_effect=RuntimeError("FATAL: database connection pool exhausted"),
        ):
            resp = client.delete(
                resources_url(
                    fake_app.app_id,
                    fake_repository.repository_id,
                    f"/{fake_resource.resource_id}",
                ),
                headers=api_headers(fake_api_key.key),
            )
            assert resp.status_code == 500
            detail = resp.json()["detail"]
            assert "FATAL" not in detail
            assert "pool exhausted" not in detail
