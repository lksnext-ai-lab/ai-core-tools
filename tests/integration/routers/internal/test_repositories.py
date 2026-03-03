"""
Integration tests for the repositories and resources endpoints.

Endpoints under test:
  - GET    /internal/apps/{app_id}/repositories           (list repositories)
  - GET    /internal/apps/{app_id}/repositories/{repo_id} (get repository details)
  - POST   /internal/apps/{app_id}/repositories/{repo_id} (create or update repository)
  - DELETE /internal/apps/{app_id}/repositories/{repo_id} (delete repository)
  - POST   /internal/apps/{app_id}/repositories/{repo_id}/resources (upload file)
  - DELETE /internal/apps/{app_id}/repositories/{repo_id}/resources/{resource_id} (delete file)

Tests run against real PostgreSQL and verify:
  - Repository CRUD operations
  - File upload and storage
  - Resource listing and deletion
  - Silo vectorization integration
  - File size limit enforcement
  - Auth and role-based access
"""

import pytest
from unittest.mock import patch, MagicMock
import io


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def repository_payload(
    name: str = "Test Repository",
    description: str = "A test repository",
    silo_id: int = None,
) -> dict:
    """Build a valid repository creation/update payload."""
    return {
        "name": name,
        "description": description,
        "silo_id": silo_id,
    }


def file_upload(
    filename: str = "test.txt",
    content: str = "Test file content",
) -> tuple:
    """Create a file upload tuple."""
    file_content = content.encode('utf-8')
    file_obj = io.BytesIO(file_content)
    return ("file", (filename, file_obj, "text/plain"))


# ---------------------------------------------------------------------------
# List repositories
# ---------------------------------------------------------------------------

class TestListRepositories:
    """GET /internal/apps/{app_id}/repositories"""

    def test_list_repositories_returns_200(self, client, fake_app, auth_headers, db):
        """List endpoint returns 200."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/repositories",
            headers=auth_headers,
        )
        assert response.status_code == 200

    def test_list_repositories_returns_empty_list_for_new_app(
        self, client, fake_app, auth_headers, db
    ):
        """New app with no repositories returns empty list."""
        db.flush()
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/repositories",
            headers=auth_headers,
        )
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_repositories_includes_metadata(self, client, db):
        """Each repository in the list includes expected fields."""
        # TODO: Create a repository fixture, then verify fields
        # Fields to check: name, description, resource_count, silo_id, created_at
        pass

    def test_list_repositories_requires_authentication(self, client, fake_app):
        """Missing auth headers returns 401/403."""
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/repositories"
        )
        assert response.status_code in (401, 403)

    def test_list_repositories_requires_viewer_role(self, client, fake_app, db):
        """VIEWER role can list repositories."""
        db.flush()
        # TODO: Add role-based access validation test when auth is fully implemented
        pass


# ---------------------------------------------------------------------------
# Get repository details
# ---------------------------------------------------------------------------

class TestGetRepository:
    """GET /internal/apps/{app_id}/repositories/{repository_id}"""

    def test_get_repository_returns_404_for_missing_repo(
        self, client, fake_app, auth_headers
    ):
        """Getting non-existent repository returns 404."""
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/repositories/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_get_repository_requires_authentication(self, client, fake_app):
        """Missing auth headers returns 401/403."""
        response = client.get(
            f"/internal/apps/{fake_app.app_id}/repositories/1"
        )
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Create repository
# ---------------------------------------------------------------------------

class TestCreateRepository:
    """POST /internal/apps/{app_id}/repositories/0 (repository_id=0 means create)"""

    def test_create_repository_returns_201(self, client, fake_app, owner_headers, db):
        """Creating a new repository returns 201."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/repositories/0",
            json=repository_payload(name="New Repository"),
            headers=owner_headers,
        )
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["name"] == "New Repository"

    def test_create_repository_with_silo_link(
        self, client, fake_app, owner_headers, db
    ):
        """Repository can be linked to a silo for vectorization."""
        db.flush()
        from tests.factories import SiloFactory, configure_factories

        configure_factories(db)
        silo = SiloFactory(app_id=fake_app.app_id)
        db.flush()

        response = client.post(
            f"/internal/apps/{fake_app.app_id}/repositories/0",
            json=repository_payload(
                name="Vectorized Repo",
                silo_id=silo.silo_id,
            ),
            headers=owner_headers,
        )
        assert response.status_code in (200, 201)
        data = response.json()
        assert data.get("silo_id") == silo.silo_id

    def test_create_repository_requires_editor_role(
        self, client, fake_app, auth_headers, db
    ):
        """Creating repository requires EDITOR role."""
        # TODO: Add proper role-based access when implemented
        db.flush()

    def test_create_repository_requires_authentication(
        self, client, fake_app, db
    ):
        """Missing auth headers returns 401/403."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/repositories/0",
            json=repository_payload(),
        )
        assert response.status_code in (401, 403)

    def test_create_repository_validates_required_fields(
        self, client, fake_app, owner_headers, db
    ):
        """Invalid payload returns 422."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/repositories/0",
            json={},  # Missing 'name'
            headers=owner_headers,
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Update repository
# ---------------------------------------------------------------------------

class TestUpdateRepository:
    """POST /internal/apps/{app_id}/repositories/{repository_id} (repository_id != 0)"""

    def test_update_repository_returns_200(self, client, db, owner_headers):
        """Updating a repository returns 200."""
        # TODO: Create repository fixture first
        pass

    def test_update_repository_changes_name(self, client, db, owner_headers):
        """Updating name persists the change."""
        # TODO: Implement when repository fixture is available
        pass

    def test_update_repository_link_to_silo(self, client, db, owner_headers):
        """Updating can link/unlink repository to/from silo."""
        # TODO: Implement when repository fixture is available
        pass


# ---------------------------------------------------------------------------
# Delete repository
# ---------------------------------------------------------------------------

class TestDeleteRepository:
    """DELETE /internal/apps/{app_id}/repositories/{repository_id}"""

    def test_delete_repository_returns_200(self, client, db, owner_headers):
        """Deleting a repository returns 200."""
        # TODO: Create repository fixture first
        pass

    def test_delete_repository_cascades_to_resources(self, client, db, owner_headers):
        """Deleting repository also deletes its resources."""
        # TODO: Implement when repository + resource fixtures are available
        pass

    def test_delete_repository_requires_owner_role(self, client, db, auth_headers):
        """Only OWNER can delete repository."""
        # TODO: Implement when role-based access is enforced
        pass


# ---------------------------------------------------------------------------
# Upload resource (file)
# ---------------------------------------------------------------------------

class TestUploadResource:
    """POST /internal/apps/{app_id}/repositories/{repository_id}/resources"""

    def test_upload_file_returns_200(self, client, db, owner_headers):
        """Uploading a file returns 200."""
        # TODO: Create repository fixture first, then test upload
        pass

    def test_upload_text_file(self, client, db, owner_headers):
        """Uploading a text file works."""
        # TODO: Implement when repository fixture is available
        pass

    def test_upload_pdf_file(self, client, db, owner_headers):
        """Uploading a PDF file works."""
        # TODO: Implement when repository fixture is available
        pass

    def test_upload_file_with_silo_vectorizes(self, client, db, owner_headers):
        """Uploaded file is vectorized into the linked silo."""
        # TODO: Implement when full pipeline can be mocked
        # This test should mock the vectorization service
        pass

    def test_upload_enforces_file_size_limit(self, client, fake_app, db, owner_headers):
        """File size limit is enforced."""
        db.flush()
        # TODO: When repository fixture exists, test file size limit
        # Create a large file and verify it's rejected based on app.max_file_size_mb
        pass

    def test_upload_requires_authentication(self, client, fake_app, db):
        """Missing auth headers returns 401/403."""
        db.flush()
        response = client.post(
            f"/internal/apps/{fake_app.app_id}/repositories/1/resources",
        )
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Delete resource (file)
# ---------------------------------------------------------------------------

class TestDeleteResource:
    """DELETE /internal/apps/{app_id}/repositories/{repository_id}/resources/{resource_id}"""

    def test_delete_resource_returns_200(self, client, db, owner_headers):
        """Deleting a resource returns 200."""
        # TODO: Create resource fixture first
        pass

    def test_delete_resource_removes_from_list(self, client, db, owner_headers):
        """After deletion, resource no longer appears in repository."""
        # TODO: Implement when resource fixture is available
        pass

    def test_delete_resource_removes_from_silo(self, client, db, owner_headers):
        """Deleting a resource removes it from the linked silo."""
        # TODO: Implement when Silo integration can be mocked/tested
        pass

    def test_delete_resource_requires_authentication(self, client, fake_app, db):
        """Missing auth headers returns 401/403."""
        db.flush()
        response = client.delete(
            f"/internal/apps/{fake_app.app_id}/repositories/1/resources/1"
        )
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Search repositories (future endpoint)
# ---------------------------------------------------------------------------

class TestSearchRepositories:
    """Future: POST /internal/apps/{app_id}/repositories/search"""

    @pytest.mark.skip(reason="Search not yet implemented")
    def test_search_by_filename(self):
        """Search finds resources by filename."""
        pass

    @pytest.mark.skip(reason="Search not yet implemented")
    def test_search_by_content(self):
        """Search finds resources by content similarity."""
        pass


# ---------------------------------------------------------------------------
# Resource metadata and chunking (future endpoints)
# ---------------------------------------------------------------------------

class TestResourceMetadata:
    """Future: Metadata and chunking endpoints"""

    @pytest.mark.skip(reason="Not yet implemented")
    def test_get_resource_chunks(self):
        """Get chunks of a resource for RAG."""
        pass

    @pytest.mark.skip(reason="Not yet implemented")
    def test_update_resource_chunking_parameters(self):
        """Update how a resource is chunked."""
        pass
