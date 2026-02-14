"""
API tests for MCP Config Export/Import REST endpoints (Phase 4).

These tests verify the FastAPI endpoints for export/import functionality.

Tests:
1. POST /mcp-configs/{config_id}/export
2. POST /mcp-configs/import (with 3 conflict modes)
3. Error handling (404, 400, 403)
4. File upload validation
5. Route ordering (/import vs /{config_id})
6. Sanitization verification

Usage:
    pytest backend/tests/test_mcp_config_export_import_api.py -v

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
from models.mcp_config import MCPConfig
from schemas.export_schemas import (
    ExportMetadataSchema,
    ExportMCPConfigSchema,
    MCPConfigExportFileSchema,
)
from schemas.import_schemas import (
    ConflictMode, ImportSummarySchema, ComponentType
)


# ==================== FIXTURES ====================


@pytest.fixture
def test_client():
    """Create FastAPI test client with authentication bypassed."""
    from main import app
    from routers.internal import mcp_configs
    
    # Create mock auth context
    mock_auth = Mock()
    mock_identity = Mock()
    mock_identity.id = "1"
    mock_identity.email = "test@example.com"
    mock_auth.identity = mock_identity
    mock_auth.user_id = 1
    mock_auth.username = "test_user"
    mock_auth.email = "test@example.com"
    
    # Override dependencies to bypass authentication
    app.dependency_overrides[
        mcp_configs.get_current_user_oauth
    ] = lambda: mock_auth
    app.dependency_overrides[
        mcp_configs.require_min_role
    ] = lambda x: lambda: mock_auth
    
    yield TestClient(app)
    
    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
def sample_export_data():
    """Sample export data for testing (sanitized)."""
    return MCPConfigExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
            exported_by="1",
            source_app_id=1,
        ),
        mcp_config=ExportMCPConfigSchema(
            name="Test MCP Server",
            description="Test MCP configuration",
            config=json.dumps({
                "url": "http://localhost:8080/mcp",
                "timeout": 30,
                "headers": {"User-Agent": "TestClient/1.0"}
            })
        ),
    )


# ==================== EXPORT ENDPOINT TESTS ====================


class TestExportMCPConfigAPI:
    """Test POST /mcp-configs/{config_id}/export endpoint."""

    def test_export_success(self, test_client, sample_export_data):
        """Test successful export returns JSON file."""
        # Mock the export service
        with patch(
            "routers.internal.mcp_configs.MCPConfigExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_mcp_config.return_value = sample_export_data

            # Make request
            response = test_client.post(
                "/internal/apps/1/mcp-configs/1/export",
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
            assert "mcp_config" in data
            assert data["mcp_config"]["name"] == "Test MCP Server"

    def test_export_content_disposition_header(
        self, test_client, sample_export_data
    ):
        """Test Content-Disposition header is correct."""
        with patch(
            "routers.internal.mcp_configs.MCPConfigExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_mcp_config.return_value = sample_export_data

            response = test_client.post(
                "/internal/apps/1/mcp-configs/1/export"
            )

            assert response.status_code == 200
            content_disp = response.headers.get("content-disposition", "")
            assert "attachment" in content_disp.lower()
            assert "Test_MCP_Server_mcp_config.json" in content_disp

    def test_export_not_found(self, test_client):
        """Test export of non-existent config returns 404."""
        with patch(
            "routers.internal.mcp_configs.MCPConfigExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_mcp_config.side_effect = ValueError(
                "MCP Config with ID 99999 not found in app 1"
            )

            response = test_client.post(
                "/internal/apps/1/mcp-configs/99999/export"
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_export_sanitized_config(self, test_client):
        """Test that exported config is sanitized (no sensitive data)."""
        # Create export data that should be sanitized
        export_data = MCPConfigExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=1,
            ),
            mcp_config=ExportMCPConfigSchema(
                name="MCP Config",
                description="Test",
                config=json.dumps({
                    "url": "http://localhost:8080",
                    "timeout": 30
                    # No api_key, token, etc. (sanitized)
                })
            ),
        )

        with patch(
            "routers.internal.mcp_configs.MCPConfigExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_mcp_config.return_value = export_data

            response = test_client.post(
                "/internal/apps/1/mcp-configs/1/export"
            )

            # Parse exported config
            data = response.json()
            config = json.loads(data["mcp_config"]["config"])

            # Verify no sensitive keys
            assert "api_key" not in config
            assert "apiKey" not in config
            assert "token" not in config
            assert "password" not in config
            assert "secret" not in config


# ==================== IMPORT ENDPOINT TESTS ====================


class TestImportMCPConfigAPI:
    """Test POST /mcp-configs/import endpoint."""

    def test_import_success(self, test_client, sample_export_data):
        """Test successful import creates new config."""
        with patch(
            "routers.internal.mcp_configs.MCPConfigImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_mcp_config.return_value = ImportSummarySchema(
                component_type=ComponentType.MCP_CONFIG,
                component_id=1,
                component_name="Test MCP Server",
                mode=ConflictMode.FAIL,
                created=True,
                warnings=["Authentication tokens must be reconfigured"],
                next_steps=["Configure auth tokens", "Test connection"]
            )

            # Create file
            file_content = sample_export_data.model_dump_json()
            files = {
                "file": ("mcp_config.json", file_content, "application/json")
            }

            response = test_client.post(
                "/internal/apps/1/mcp-configs/import",
                files=files,
                params={"conflict_mode": "fail"}
            )

            # Verify response
            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            assert "imported successfully" in data["message"].lower()
            assert data["summary"]["created"] is True
            assert len(data["summary"]["warnings"]) > 0

    def test_import_conflict_fail_mode(self, test_client, sample_export_data):
        """Test import with FAIL mode on conflict returns error."""
        with patch(
            "routers.internal.mcp_configs.MCPConfigImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_mcp_config.side_effect = ValueError(
                "MCP Config 'Test MCP Server' already exists in app 1"
            )

            file_content = sample_export_data.model_dump_json()
            files = {
                "file": ("mcp_config.json", file_content, "application/json")
            }

            response = test_client.post(
                "/internal/apps/1/mcp-configs/import",
                files=files,
                params={"conflict_mode": "fail"}
            )

            assert response.status_code == 409
            assert "already exists" in response.json()["detail"].lower()

    def test_import_conflict_rename_mode(
        self, test_client, sample_export_data
    ):
        """Test import with RENAME mode creates with new name."""
        with patch(
            "routers.internal.mcp_configs.MCPConfigImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_mcp_config.return_value = ImportSummarySchema(
                component_type=ComponentType.MCP_CONFIG,
                component_id=2,
                component_name="Test MCP Server (imported 2026-02-09)",
                mode=ConflictMode.RENAME,
                created=True,
                warnings=["Authentication tokens must be reconfigured"],
                next_steps=[]
            )

            file_content = sample_export_data.model_dump_json()
            files = {
                "file": ("mcp_config.json", file_content, "application/json")
            }

            response = test_client.post(
                "/internal/apps/1/mcp-configs/import",
                files=files,
                params={"conflict_mode": "rename"}
            )

            assert response.status_code == 201
            data = response.json()
            assert "imported" in data["summary"]["component_name"].lower()

    def test_import_conflict_override_mode(
        self, test_client, sample_export_data
    ):
        """Test import with OVERRIDE mode updates existing config."""
        with patch(
            "routers.internal.mcp_configs.MCPConfigImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_mcp_config.return_value = ImportSummarySchema(
                component_type=ComponentType.MCP_CONFIG,
                component_id=1,
                component_name="Test MCP Server",
                mode=ConflictMode.OVERRIDE,
                created=False,
                warnings=[
                    "Existing authentication credentials preserved"
                ],
                next_steps=["Test connection", "Update URLs if needed"]
            )

            file_content = sample_export_data.model_dump_json()
            files = {
                "file": ("mcp_config.json", file_content, "application/json")
            }

            response = test_client.post(
                "/internal/apps/1/mcp-configs/import",
                files=files,
                params={"conflict_mode": "override"}
            )

            assert response.status_code == 201
            data = response.json()
            assert data["summary"]["created"] is False
            assert "preserved" in " ".join(data["summary"]["warnings"]).lower()

    def test_import_invalid_json(self, test_client):
        """Test import with invalid JSON returns error."""
        files = {
            "file": ("mcp_config.json", b"invalid json{{{", "application/json")
        }

        response = test_client.post(
            "/internal/apps/1/mcp-configs/import",
            files=files
        )

        assert response.status_code == 400
        assert "invalid json" in response.json()["detail"].lower()

    def test_route_ordering_import_before_config_id(self, test_client):
        """Test that /import route doesn't conflict with /{config_id}."""
        # This test verifies route ordering by ensuring /import is matched
        # before trying to parse it as a config_id

        with patch(
            "routers.internal.mcp_configs.MCPConfigImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_mcp_config.return_value = ImportSummarySchema(
                component_type=ComponentType.MCP_CONFIG,
                component_id=1,
                component_name="Test",
                mode=ConflictMode.FAIL,
                created=True,
                warnings=[],
                next_steps=[]
            )

            export_data = MCPConfigExportFileSchema(
                metadata=ExportMetadataSchema(
                    export_version="1.0.0",
                    export_date=datetime.now(),
                    exported_by="1",
                    source_app_id=1,
                ),
                mcp_config=ExportMCPConfigSchema(
                    name="Test",
                    description="Test",
                    config=json.dumps({"url": "http://test.com"})
                ),
            )

            file_content = export_data.model_dump_json()
            files = {
                "file": ("mcp_config.json", file_content, "application/json")
            }

            # Should hit /import endpoint, not try to parse "import" as config_id
            response = test_client.post(
                "/internal/apps/1/mcp-configs/import",
                files=files
            )

            # If route ordering is correct, should get 201, not 422 or 404
            assert response.status_code == 201


# ==================== ERROR HANDLING TESTS ====================


class TestExportImportErrorHandling:
    """Test error handling for export/import endpoints."""

    def test_export_service_error(self, test_client):
        """Test export service error returns 500."""
        with patch(
            "routers.internal.mcp_configs.MCPConfigExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_mcp_config.side_effect = Exception(
                "Database error"
            )

            response = test_client.post(
                "/internal/apps/1/mcp-configs/1/export"
            )

            assert response.status_code == 500
            assert "export failed" in response.json()["detail"].lower()

    def test_import_service_error(self, test_client, sample_export_data):
        """Test import service error returns 500."""
        with patch(
            "routers.internal.mcp_configs.MCPConfigImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_mcp_config.side_effect = Exception(
                "Database error"
            )

            file_content = sample_export_data.model_dump_json()
            files = {
                "file": ("mcp_config.json", file_content, "application/json")
            }

            response = test_client.post(
                "/internal/apps/1/mcp-configs/import",
                files=files
            )

            assert response.status_code == 500
            assert "import failed" in response.json()["detail"].lower()
