"""
API tests for Embedding Service Export/Import REST endpoints (Phase 2).

These tests verify the FastAPI endpoints for export/import functionality.

Tests:
1. POST /embedding-services/{service_id}/export
2. POST /embedding-services/import (with 3 conflict modes)
3. Error handling (404, 400, 403)
4. File upload validation

Usage:
    pytest backend/tests/test_embedding_export_import_api.py -v

Note: These tests use mocking to avoid requiring authentication.
"""

import pytest
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from io import BytesIO
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

# Add parent directory to path
backend_path = Path(__file__).parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from main import app
from models.embedding_service import EmbeddingService, EmbeddingProvider
from schemas.export_schemas import (
    ExportMetadataSchema,
    ExportEmbeddingServiceSchema,
    EmbeddingServiceExportFileSchema,
)
from schemas.import_schemas import ConflictMode, ImportSummarySchema, ComponentType


# ==================== FIXTURES ====================


@pytest.fixture
def test_client():
    """Create FastAPI test client with authentication bypassed."""
    from main import app
    from routers.internal import embedding_services
    
    # Create mock auth context with proper structure
    mock_auth = Mock()
    mock_identity = Mock()
    mock_identity.id = "1"
    mock_identity.email = "test@example.com"
    mock_auth.identity = mock_identity
    mock_auth.user_id = 1
    mock_auth.username = "test_user"
    mock_auth.email = "test@example.com"
    
    # Override dependencies to bypass authentication
    app.dependency_overrides[embedding_services.get_current_user_oauth] = lambda: mock_auth
    app.dependency_overrides[embedding_services.require_min_role] = lambda x: lambda: mock_auth
    
    yield TestClient(app)
    
    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
def sample_export_data():
    """Sample export data for testing."""
    return EmbeddingServiceExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
            exported_by="1",
            source_app_id=1,
        ),
        embedding_service=ExportEmbeddingServiceSchema(
            name="Test Embedding Service",
            api_key=None,
            provider=EmbeddingProvider.OpenAI,
            model_name="text-embedding-3-large",
            endpoint="https://api.openai.com/v1",
            description=None,
        ),
    )


# ==================== EXPORT ENDPOINT TESTS ====================


class TestExportEmbeddingServiceAPI:
    """Test POST /embedding-services/{service_id}/export endpoint."""

    def test_export_success(self, test_client, sample_export_data):
        """Test successful export returns JSON file."""
        # Mock the export service
        with patch(
            "routers.internal.embedding_services.EmbeddingServiceExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_embedding_service.return_value = sample_export_data

            # Make request
            response = test_client.post(
                "/internal/apps/1/embedding-services/1/export",
                headers={"Authorization": "Bearer test-token"},
            )

            # Verify response
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/json"
            assert (
                "attachment"
                in response.headers.get("content-disposition", "").lower()
            )

            # Verify JSON structure
            data = response.json()
            assert "metadata" in data
            assert "embedding_service" in data
            assert data["embedding_service"]["api_key"] is None
            assert (
                data["embedding_service"]["name"] == "Test Embedding Service"
            )

    def test_export_service_not_found(self, test_client):
        """Test export returns 404 when service doesn't exist."""
        # Mock the export service to raise ValueError
        with patch(
            "routers.internal.embedding_services.EmbeddingServiceExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_embedding_service.side_effect = ValueError(
                "Embedding Service with ID 999 not found in app 1"
            )

            # Make request
            response = test_client.post(
                "/internal/apps/1/embedding-services/999/export",
                headers={"Authorization": "Bearer test-token"},
            )

            # Verify response
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_export_api_key_sanitized(self, test_client, sample_export_data):
        """Test that exported data has API key set to None."""
        # Mock the export service
        with patch(
            "routers.internal.embedding_services.EmbeddingServiceExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_embedding_service.return_value = sample_export_data

            # Make request
            response = test_client.post(
                "/internal/apps/1/embedding-services/1/export",
                headers={"Authorization": "Bearer test-token"},
            )

            # Verify API key is None
            data = response.json()
            assert data["embedding_service"]["api_key"] is None


# ==================== IMPORT ENDPOINT TESTS ====================


class TestImportEmbeddingServiceAPI:
    """Test POST /embedding-services/import endpoint."""

    def test_import_success_fail_mode(
        self,
        test_client,
        sample_export_data,
    ):
        """Test successful import with FAIL conflict mode."""
        # Mock the import service
        with patch(
            "routers.internal.embedding_services.EmbeddingServiceImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_embedding_service.return_value = (
                ImportSummarySchema(
                    component_type=ComponentType.EMBEDDING_SERVICE,
                    component_id=1,
                    component_name="Test Embedding Service",
                    mode=ConflictMode.FAIL,
                    created=True,
                    warnings=[],
                    next_steps=[
                        "Configure API key for the imported Embedding Service"
                    ],
                )
            )

            # Create file to upload
            file_content = json.dumps(
                sample_export_data.model_dump(mode="json"), default=str
            ).encode()
            files = {
                "file": (
                    "embedding_service.json",
                    BytesIO(file_content),
                    "application/json",
                )
            }

            # Make request
            response = test_client.post(
                "/internal/apps/1/embedding-services/import?conflict_mode=fail",
                headers={"Authorization": "Bearer test-token"},
                files=files,
            )

            # Verify response
            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            assert "imported successfully" in data["message"].lower()
            assert data["summary"]["component_id"] == 1
            assert data["summary"]["created"] is True

    def test_import_success_rename_mode(
        self,
        test_client,
        sample_export_data,
    ):
        """Test successful import with RENAME conflict mode."""
        # Mock the import service
        with patch(
            "routers.internal.embedding_services.EmbeddingServiceImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_embedding_service.return_value = (
                ImportSummarySchema(
                    component_type=ComponentType.EMBEDDING_SERVICE,
                    component_id=2,
                    component_name="Test Embedding Service (imported 2026-02-09)",
                    mode=ConflictMode.RENAME,
                    created=True,
                    warnings=[],
                    next_steps=[
                        "Configure API key for the imported Embedding Service"
                    ],
                )
            )

            # Create file to upload
            file_content = json.dumps(
                sample_export_data.model_dump(mode="json"), default=str
            ).encode()
            files = {
                "file": (
                    "embedding_service.json",
                    BytesIO(file_content),
                    "application/json",
                )
            }

            # Make request
            response = test_client.post(
                "/internal/apps/1/embedding-services/import?conflict_mode=rename",
                headers={"Authorization": "Bearer test-token"},
                files=files,
            )

            # Verify response
            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            assert "(imported" in data["summary"]["component_name"]

    def test_import_success_override_mode(
        self,
        test_client,
        sample_export_data,
    ):
        """Test successful import with OVERRIDE conflict mode."""
        # Mock the import service
        with patch(
            "routers.internal.embedding_services.EmbeddingServiceImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_embedding_service.return_value = (
                ImportSummarySchema(
                    component_type=ComponentType.EMBEDDING_SERVICE,
                    component_id=1,
                    component_name="Test Embedding Service",
                    mode=ConflictMode.OVERRIDE,
                    created=False,
                    warnings=["Existing API key preserved"],
                    next_steps=[],
                )
            )

            # Create file to upload
            file_content = json.dumps(
                sample_export_data.model_dump(mode="json"), default=str
            ).encode()
            files = {
                "file": (
                    "embedding_service.json",
                    BytesIO(file_content),
                    "application/json",
                )
            }

            # Make request
            response = test_client.post(
                "/internal/apps/1/embedding-services/import?conflict_mode=override",
                headers={"Authorization": "Bearer test-token"},
                files=files,
            )

            # Verify response
            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            assert data["summary"]["created"] is False

    def test_import_conflict_fail_mode(
        self,
        test_client,
        sample_export_data,
    ):
        """Test import fails when service exists with FAIL mode."""
        # Mock the import service to raise ValueError
        with patch(
            "routers.internal.embedding_services.EmbeddingServiceImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_embedding_service.side_effect = ValueError(
                "Embedding Service 'Test Embedding Service' already exists in app 1"
            )

            # Create file to upload
            file_content = json.dumps(
                sample_export_data.model_dump(mode="json"), default=str
            ).encode()
            files = {
                "file": (
                    "embedding_service.json",
                    BytesIO(file_content),
                    "application/json",
                )
            }

            # Make request
            response = test_client.post(
                "/internal/apps/1/embedding-services/import?conflict_mode=fail",
                headers={"Authorization": "Bearer test-token"},
                files=files,
            )

            # Verify response
            assert response.status_code == 400
            assert "already exists" in response.json()["detail"].lower()

    def test_import_invalid_json(self, test_client):
        """Test import fails with invalid JSON file."""
        # Create invalid JSON file
        files = {
            "file": (
                "invalid.json",
                BytesIO(b"not valid json"),
                "application/json",
            )
        }

        # Make request
        response = test_client.post(
            "/internal/apps/1/embedding-services/import?conflict_mode=fail",
            headers={"Authorization": "Bearer test-token"},
            files=files,
        )

        # Verify response
        assert response.status_code in [400, 500]

    def test_import_with_custom_name(
        self,
        test_client,
        sample_export_data,
    ):
        """Test import with custom name parameter."""
        # Mock the import service
        with patch(
            "routers.internal.embedding_services.EmbeddingServiceImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_embedding_service.return_value = (
                ImportSummarySchema(
                    component_type=ComponentType.EMBEDDING_SERVICE,
                    component_id=3,
                    component_name="Custom Name for Import",
                    mode=ConflictMode.RENAME,
                    created=True,
                    warnings=[],
                    next_steps=[
                        "Configure API key for the imported Embedding Service"
                    ],
                )
            )

            # Create file to upload
            file_content = json.dumps(
                sample_export_data.model_dump(mode="json"), default=str
            ).encode()
            files = {
                "file": (
                    "embedding_service.json",
                    BytesIO(file_content),
                    "application/json",
                )
            }

            # Make request with custom name
            response = test_client.post(
                "/internal/apps/1/embedding-services/import?conflict_mode=rename&new_name=Custom%20Name%20for%20Import",
                headers={"Authorization": "Bearer test-token"},
                files=files,
            )

            # Verify response
            assert response.status_code == 201
            data = response.json()
            assert data["summary"]["component_name"] == "Custom Name for Import"

            # Verify import service was called with new_name
            mock_service.import_embedding_service.assert_called_once()
            call_args = mock_service.import_embedding_service.call_args
            # Arguments are positional: (schema, app_id, mode, new_name)
            assert call_args.args[3] == "Custom Name for Import"


# ==================== ROUTE ORDERING TESTS ====================


class TestRouteOrdering:
    """Test that static /import route comes before dynamic /{service_id} route."""

    def test_import_route_not_confused_with_service_id(
        self, test_client, sample_export_data
    ):
        """Test that /import is not treated as service_id 'import'."""
        # Mock the import service
        with patch(
            "routers.internal.embedding_services.EmbeddingServiceImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_embedding_service.return_value = (
                ImportSummarySchema(
                    component_type=ComponentType.EMBEDDING_SERVICE,
                    component_id=1,
                    component_name="Test",
                    mode=ConflictMode.FAIL,
                    created=True,
                    warnings=[],
                    next_steps=[],
                )
            )

            # Create file to upload
            file_content = json.dumps(
                sample_export_data.model_dump(mode="json"), default=str
            ).encode()
            files = {
                "file": (
                    "embedding_service.json",
                    BytesIO(file_content),
                    "application/json",
                )
            }

            # Make request - should hit /import endpoint, not /{service_id}
            response = test_client.post(
                "/internal/apps/1/embedding-services/import?conflict_mode=fail",
                headers={"Authorization": "Bearer test-token"},
                files=files,
            )

            # Should succeed with 201, not 404 or 422
            assert response.status_code == 201
            assert response.json()["success"] is True
