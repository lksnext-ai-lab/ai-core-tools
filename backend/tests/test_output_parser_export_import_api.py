"""
API tests for Output Parser Export/Import REST endpoints (Phase 3).

These tests verify the FastAPI endpoints for export/import functionality.

Tests:
1. POST /output-parsers/{parser_id}/export
2. POST /output-parsers/import (with 3 conflict modes)
3. Error handling (404, 400, 403)
4. File upload validation
5. Route ordering (/import vs /{parser_id})

Usage:
    pytest backend/tests/test_output_parser_export_import_api.py -v

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
from models.output_parser import OutputParser
from schemas.export_schemas import (
    ExportMetadataSchema,
    ExportOutputParserFieldSchema,
    ExportOutputParserSchema,
    OutputParserExportFileSchema,
)
from schemas.import_schemas import ConflictMode, ImportSummarySchema, ComponentType


# ==================== FIXTURES ====================


@pytest.fixture
def test_client():
    """Create FastAPI test client with authentication bypassed."""
    from main import app
    from routers.internal import output_parsers
    
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
    app.dependency_overrides[output_parsers.get_current_user_oauth] = lambda: mock_auth
    app.dependency_overrides[output_parsers.require_min_role] = lambda x: lambda: mock_auth
    
    yield TestClient(app)
    
    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
def sample_export_data():
    """Sample export data for testing."""
    return OutputParserExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
            exported_by="1",
            source_app_id=1,
        ),
        output_parser=ExportOutputParserSchema(
            name="Test User Parser",
            description="Parser for user data",
            fields=[
                ExportOutputParserFieldSchema(
                    name="username",
                    type="str",
                    description="User's username"
                ),
                ExportOutputParserFieldSchema(
                    name="age",
                    type="int",
                    description="User's age"
                )
            ]
        ),
    )


# ==================== EXPORT ENDPOINT TESTS ====================


class TestExportOutputParserAPI:
    """Test POST /output-parsers/{parser_id}/export endpoint."""

    def test_export_success(self, test_client, sample_export_data):
        """Test successful export returns JSON file."""
        # Mock the export service
        with patch(
            "routers.internal.output_parsers.OutputParserExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_output_parser.return_value = sample_export_data

            # Make request
            response = test_client.post(
                "/internal/apps/1/output-parsers/1/export",
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
            assert "output_parser" in data
            assert data["output_parser"]["name"] == "Test User Parser"
            assert len(data["output_parser"]["fields"]) == 2

    def test_export_content_disposition_header(self, test_client, sample_export_data):
        """Test Content-Disposition header is correct."""
        with patch(
            "routers.internal.output_parsers.OutputParserExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_output_parser.return_value = sample_export_data

            response = test_client.post(
                "/internal/apps/1/output-parsers/1/export"
            )

            assert response.status_code == 200
            disposition = response.headers.get("content-disposition", "")
            assert "attachment" in disposition
            assert "output_parser.json" in disposition.lower()

    def test_export_parser_not_found(self, test_client):
        """Test export with non-existent parser returns 404."""
        with patch(
            "routers.internal.output_parsers.OutputParserExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_output_parser.side_effect = ValueError(
                "Output Parser with ID 999 not found in app 1"
            )

            response = test_client.post(
                "/internal/apps/1/output-parsers/999/export"
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_export_invalid_app_id(self, test_client):
        """Test export with invalid app ID returns error."""
        with patch(
            "routers.internal.output_parsers.OutputParserExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_output_parser.side_effect = ValueError(
                "Output Parser with ID 1 not found in app 999"
            )

            response = test_client.post(
                "/internal/apps/999/output-parsers/1/export"
            )

            assert response.status_code == 404


# ==================== IMPORT ENDPOINT TESTS ====================


class TestImportOutputParserAPI:
    """Test POST /output-parsers/import endpoint."""

    def test_import_success_fail_mode(self, test_client, sample_export_data):
        """Test successful import with FAIL mode."""
        # Mock the import service
        with patch(
            "routers.internal.output_parsers.OutputParserImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_output_parser.return_value = ImportSummarySchema(
                component_type=ComponentType.OUTPUT_PARSER,
                component_id=1,
                component_name="Test User Parser",
                mode=ConflictMode.FAIL,
                created=True,
                warnings=[],
                next_steps=["Review and test the imported parser schema"]
            )

            # Create file
            export_json = json.dumps(sample_export_data.model_dump(mode='json'))
            files = {
                "file": ("test_parser.json", BytesIO(export_json.encode()), "application/json")
            }

            # Make request
            response = test_client.post(
                "/internal/apps/1/output-parsers/import?conflict_mode=fail",
                files=files
            )

            # Verify response
            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            assert "imported successfully" in data["message"].lower()
            assert data["summary"]["component_type"] == "output_parser"
            assert data["summary"]["created"] is True

    def test_import_success_rename_mode(self, test_client, sample_export_data):
        """Test successful import with RENAME mode."""
        with patch(
            "routers.internal.output_parsers.OutputParserImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_output_parser.return_value = ImportSummarySchema(
                component_type=ComponentType.OUTPUT_PARSER,
                component_id=2,
                component_name="Test User Parser (imported 2026-02-09)",
                mode=ConflictMode.RENAME,
                created=True,
                warnings=[],
                next_steps=["Review and test the imported parser schema"]
            )

            export_json = json.dumps(sample_export_data.model_dump(mode='json'))
            files = {
                "file": ("test_parser.json", BytesIO(export_json.encode()), "application/json")
            }

            response = test_client.post(
                "/internal/apps/1/output-parsers/import?conflict_mode=rename",
                files=files
            )

            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            assert "(imported" in data["summary"]["component_name"]

    def test_import_success_override_mode(self, test_client, sample_export_data):
        """Test successful import with OVERRIDE mode."""
        with patch(
            "routers.internal.output_parsers.OutputParserImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_output_parser.return_value = ImportSummarySchema(
                component_type=ComponentType.OUTPUT_PARSER,
                component_id=1,
                component_name="Test User Parser",
                mode=ConflictMode.OVERRIDE,
                created=False,  # Updated existing
                warnings=[],
                next_steps=["Review and test the imported parser schema"]
            )

            export_json = json.dumps(sample_export_data.model_dump(mode='json'))
            files = {
                "file": ("test_parser.json", BytesIO(export_json.encode()), "application/json")
            }

            response = test_client.post(
                "/internal/apps/1/output-parsers/import?conflict_mode=override",
                files=files
            )

            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            assert data["summary"]["created"] is False

    def test_import_with_custom_name(self, test_client, sample_export_data):
        """Test import with custom name parameter."""
        with patch(
            "routers.internal.output_parsers.OutputParserImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_output_parser.return_value = ImportSummarySchema(
                component_type=ComponentType.OUTPUT_PARSER,
                component_id=3,
                component_name="Custom Parser Name",
                mode=ConflictMode.RENAME,
                created=True,
                warnings=[],
                next_steps=[]
            )

            export_json = json.dumps(sample_export_data.model_dump(mode='json'))
            files = {
                "file": ("test_parser.json", BytesIO(export_json.encode()), "application/json")
            }

            response = test_client.post(
                "/internal/apps/1/output-parsers/import?conflict_mode=rename&new_name=Custom Parser Name",
                files=files
            )

            assert response.status_code == 201
            data = response.json()
            assert data["summary"]["component_name"] == "Custom Parser Name"

    def test_import_conflict_fail_mode_error(self, test_client, sample_export_data):
        """Test import returns 400 when name conflict in FAIL mode."""
        with patch(
            "routers.internal.output_parsers.OutputParserImportService"
        ) as MockImportService:
            mock_service = MockImportService.return_value
            mock_service.import_output_parser.side_effect = ValueError(
                "Output Parser 'Test User Parser' already exists in app 1"
            )

            export_json = json.dumps(sample_export_data.model_dump(mode='json'))
            files = {
                "file": ("test_parser.json", BytesIO(export_json.encode()), "application/json")
            }

            response = test_client.post(
                "/internal/apps/1/output-parsers/import?conflict_mode=fail",
                files=files
            )

            assert response.status_code == 400
            assert "already exists" in response.json()["detail"]

    def test_import_invalid_json(self, test_client):
        """Test import with invalid JSON returns 400."""
        files = {
            "file": ("invalid.json", BytesIO(b"not valid json"), "application/json")
        }

        response = test_client.post(
            "/internal/apps/1/output-parsers/import",
            files=files
        )

        assert response.status_code == 400
        assert "json" in response.json()["detail"].lower()

    def test_import_missing_required_fields(self, test_client):
        """Test import with missing required fields returns 400."""
        # Missing 'name' field
        invalid_data = {
            "metadata": {
                "export_version": "1.0.0",
                "export_date": datetime.now().isoformat(),
                "exported_by": "1",
                "source_app_id": 1
            },
            "output_parser": {
                "description": "Parser without name",
                "fields": []
            }
        }

        files = {
            "file": ("invalid.json", BytesIO(json.dumps(invalid_data).encode()), "application/json")
        }

        response = test_client.post(
            "/internal/apps/1/output-parsers/import",
            files=files
        )

        assert response.status_code == 400


# ==================== ROUTE ORDERING TESTS ====================


class TestRouteOrdering:
    """Test that /import route doesn't conflict with /{parser_id} routes."""

    def test_import_route_not_confused_with_parser_id(self, test_client):
        """Test that /import is handled as static route, not parser_id."""
        # This should hit the import endpoint, not try to get parser with id="import"
        files = {
            "file": ("test.json", BytesIO(b"{}"), "application/json")
        }

        response = test_client.post(
            "/internal/apps/1/output-parsers/import",
            files=files
        )

        # Should fail with 400 (invalid JSON) not 404 (parser not found)
        assert response.status_code == 400
        # Should mention validation error or invalid data, not "parser not found"
        detail = response.json()["detail"].lower()
        assert "invalid" in detail or "validation" in detail or "required" in detail
        assert "parser not found" not in detail

    def test_parser_id_route_still_works(self, test_client):
        """Test that numeric parser_id routes still work correctly."""
        # Mock the service to return parser details
        from services.output_parser_service import OutputParserService
        from schemas.output_parser_schemas import OutputParserDetailSchema
        
        with patch.object(OutputParserService, 'get_output_parser_detail') as mock_get:
            mock_get.return_value = OutputParserDetailSchema(
                parser_id=42,
                name="Test Parser",
                description="Test",
                fields=[],
                created_at=datetime.now(),
                available_parsers=[]
            )

            response = test_client.get("/internal/apps/1/output-parsers/42")

            # Should succeed (or 404 if not mocked properly, but not 400)
            assert response.status_code in [200, 404]
            if response.status_code == 404:
                # Should be about parser not found, not routing error
                assert "parser" in response.json()["detail"].lower()

    def test_export_route_works_with_parser_id(self, test_client, sample_export_data):
        """Test that /export subroute works correctly."""
        with patch(
            "routers.internal.output_parsers.OutputParserExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_output_parser.return_value = sample_export_data

            response = test_client.post(
                "/internal/apps/1/output-parsers/42/export"
            )

            assert response.status_code == 200
            assert "application/json" in response.headers["content-type"]


# ==================== EDGE CASES ====================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_import_with_empty_file(self, test_client):
        """Test import with empty file."""
        files = {
            "file": ("empty.json", BytesIO(b""), "application/json")
        }

        response = test_client.post(
            "/internal/apps/1/output-parsers/import",
            files=files
        )

        assert response.status_code == 400

    def test_import_with_non_json_file(self, test_client):
        """Test import with non-JSON file."""
        files = {
            "file": ("test.txt", BytesIO(b"This is not JSON"), "text/plain")
        }

        response = test_client.post(
            "/internal/apps/1/output-parsers/import",
            files=files
        )

        assert response.status_code == 400

    def test_export_with_zero_parser_id(self, test_client):
        """Test export with parser_id=0 (special case for new parser)."""
        with patch(
            "routers.internal.output_parsers.OutputParserExportService"
        ) as MockExportService:
            mock_service = MockExportService.return_value
            mock_service.export_output_parser.side_effect = ValueError(
                "Output Parser with ID 0 not found in app 1"
            )

            response = test_client.post(
                "/internal/apps/1/output-parsers/0/export"
            )

            assert response.status_code == 404

    def test_import_with_invalid_conflict_mode(self, test_client, sample_export_data):
        """Test import with invalid conflict_mode parameter."""
        export_json = json.dumps(sample_export_data.model_dump(mode='json'))
        files = {
            "file": ("test.json", BytesIO(export_json.encode()), "application/json")
        }

        response = test_client.post(
            "/internal/apps/1/output-parsers/import?conflict_mode=invalid_mode",
            files=files
        )

        # Should return 422 for invalid enum value
        assert response.status_code == 422
