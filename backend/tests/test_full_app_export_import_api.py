"""
API tests for Full App Export/Import REST endpoints (Phase 8).

These tests verify the FastAPI endpoints for full app export/import functionality.

Tests:
1. POST /apps/{app_id}/export-full
2. POST /apps/import-full (with different target modes and selections)
3. Error handling (404, 400)
4. File upload validation
5. Selective component import

Usage:
    pytest backend/tests/test_full_app_export_import_api.py -v

Note: These tests use mocking to avoid requiring authentication.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

# Add parent directory to path
import sys
backend_path = Path(__file__).parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from main import app
from schemas.export_schemas import (
    AppExportFileSchema,
    ExportMetadataSchema,
    ExportAppSchema,
    ExportAIServiceSchema,
    ExportEmbeddingServiceSchema,
    ExportOutputParserSchema,
    ExportOutputParserFieldSchema,
    ExportMCPConfigSchema,
    ExportSiloSchema,
    ExportAgentSchema,
)
from schemas.import_schemas import (
    ConflictMode,
    ImportTargetMode,
    FullAppImportSummarySchema,
)


# ==================== FIXTURES ====================


@pytest.fixture
def test_client():
    """Create FastAPI test client with authentication bypassed."""
    from main import app
    from routers.internal import apps
    
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
    app.dependency_overrides[apps.get_current_user_oauth] = lambda: mock_auth
    app.dependency_overrides[apps.require_min_role] = lambda x: lambda: mock_auth
    
    yield TestClient(app)
    
    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
def sample_export_data():
    """Sample full app export data for testing."""
    return AppExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
            exported_by="1",
            source_app_id=1,
        ),
        app=ExportAppSchema(
            name="Test App",
            description="Test app for export/import",
        ),
        ai_services=[
            ExportAIServiceSchema(
                name="GPT-4",
                api_key=None,
                provider="OpenAI",
                model_name="gpt-4",
                endpoint="https://api.openai.com/v1",
                description=None,
                api_version="v1",
            )
        ],
        embedding_services=[
            ExportEmbeddingServiceSchema(
                name="OpenAI Embeddings",
                api_key=None,
                provider="OpenAI",
                model_name="text-embedding-3-small",
                endpoint="https://api.openai.com/v1",
                description=None,
                api_version=None,
            )
        ],
        output_parsers=[
            ExportOutputParserSchema(
                name="Contact Parser",
                description="Parse contacts",
                fields=[
                    ExportOutputParserFieldSchema(
                        name="name",
                        type="str",
                        description="Contact name",
                    )
                ],
            )
        ],
        mcp_configs=[
            ExportMCPConfigSchema(
                name="Test MCP",
                description="Test MCP config",
                config='{"test": {"command": "test"}}',
            )
        ],
        silos=[
            ExportSiloSchema(
                name="Test Silo",
                description="Test silo",
                type="CUSTOM",
                embedding_service_name="OpenAI Embeddings",
                output_parser_name="Contact Parser",
            )
        ],
        repositories=[],
        agents=[
            ExportAgentSchema(
                name="Test Agent",
                description="Test agent",
                system_prompt="You are a test agent",
                prompt_template=None,
                service_name="GPT-4",
                silo_name="Test Silo",
                output_parser_name=None,
                agent_tool_refs=[],
                agent_mcp_refs=[],
                has_memory=True,
                memory_max_messages=10,
                memory_max_tokens=4000,
                memory_summarize_threshold=10,
                temperature=0.7,
            )
        ],
    )


# ==================== EXPORT TESTS ====================


class TestFullAppExportAPI:
    """Tests for POST /apps/{app_id}/export-full endpoint."""
    
    @patch("services.full_app_export_service.FullAppExportService.export_full_app")
    def test_export_full_app_success(
        self, mock_export, test_client, sample_export_data
    ):
        """Test successful full app export."""
        # Mock export service to return sample data
        mock_export.return_value = sample_export_data
        
        # Make request
        response = test_client.post("/internal/apps/1/export-full")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "metadata" in data
        assert "app" in data
        assert "ai_services" in data
        assert "embedding_services" in data
        assert "output_parsers" in data
        assert "mcp_configs" in data
        assert "silos" in data
        assert "repositories" in data
        assert "agents" in data
        
        # Verify content
        assert data["app"]["name"] == "Test App"
        assert len(data["ai_services"]) == 1
        assert len(data["embedding_services"]) == 1
        assert len(data["output_parsers"]) == 1
        assert len(data["mcp_configs"]) == 1
        assert len(data["silos"]) == 1
        assert len(data["agents"]) == 1
        
        # Verify export service was called
        mock_export.assert_called_once()
    
    @patch("services.full_app_export_service.FullAppExportService.export_full_app")
    def test_export_nonexistent_app(self, mock_export, test_client):
        """Test export of non-existent app returns 404."""
        # Mock export service to raise ValueError
        mock_export.side_effect = ValueError("App with ID 999 not found")
        
        # Make request
        response = test_client.post("/internal/apps/999/export-full")
        
        # Verify 404 response
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    @patch("services.full_app_export_service.FullAppExportService.export_full_app")
    def test_export_secrets_sanitized(
        self, mock_export, test_client, sample_export_data
    ):
        """Test that export contains no API keys or secrets."""
        # Mock export service
        mock_export.return_value = sample_export_data
        
        # Make request
        response = test_client.post("/internal/apps/1/export-full")
        
        # Verify response
        assert response.status_code == 200
        
        # Convert to JSON string and search for secrets
        export_json = response.text
        
        # Should NOT contain any actual API keys (sk- prefix)
        assert "sk-" not in export_json
        # api_key fields should be null
        assert '"api_key":null' in export_json or '"api_key": null' in export_json


# ==================== IMPORT TESTS ====================


class TestFullAppImportAPI:
    """Tests for POST /apps/import-full endpoint."""
    
    @patch("services.full_app_import_service.FullAppImportService.import_full_app")
    @patch("repositories.app_repository.AppRepository.get_by_id")
    def test_import_into_existing_app_success(
        self, mock_get_app, mock_import, test_client, sample_export_data
    ):
        """Test successful import into existing app."""
        # Mock app exists
        mock_app = Mock()
        mock_app.name = "Target App"
        mock_get_app.return_value = mock_app
        
        # Mock import service
        mock_summary = FullAppImportSummarySchema(
            app_name="Target App",
            app_id=1,
            total_components=7,
            components_imported={
                "ai_services": 1,
                "embedding_services": 1,
                "output_parsers": 1,
                "mcp_configs": 1,
                "silos": 1,
                "agents": 1,
            },
            components_skipped={},
            total_warnings=[],
            total_errors=[],
            duration_seconds=0.5,
        )
        mock_import.return_value = mock_summary
        
        # Create file content
        export_json = sample_export_data.model_dump_json()
        
        # Make request
        response = test_client.post(
            "/internal/apps/import-full?target_mode=existing_app&target_app_id=1&conflict_mode=fail",
            files={"file": ("export.json", export_json, "application/json")},
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "summary" in data
        assert data["summary"]["total_components"] == 7
        assert data["summary"]["app_id"] == 1
    
    @patch("services.full_app_import_service.FullAppImportService.import_full_app")
    def test_import_as_new_app_success(
        self, mock_import, test_client, sample_export_data
    ):
        """Test successful import creating new app."""
        # Mock import service
        mock_summary = FullAppImportSummarySchema(
            app_name="Test App (imported 20260210_120000)",
            app_id=2,
            total_components=7,
            components_imported={
                "ai_services": 1,
                "embedding_services": 1,
                "output_parsers": 1,
                "mcp_configs": 1,
                "silos": 1,
                "agents": 1,
            },
            components_skipped={},
            total_warnings=[],
            total_errors=[],
            duration_seconds=0.8,
        )
        mock_import.return_value = mock_summary
        
        # Create file content
        export_json = sample_export_data.model_dump_json()
        
        # Make request
        response = test_client.post(
            "/internal/apps/import-full?target_mode=new_app&conflict_mode=fail",
            files={"file": ("export.json", export_json, "application/json")},
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["summary"]["app_id"] == 2
        assert "imported" in data["summary"]["app_name"].lower()
    
    @patch("services.full_app_import_service.FullAppImportService.import_full_app")
    @patch("repositories.app_repository.AppRepository.get_by_id")
    def test_import_selective_components(
        self, mock_get_app, mock_import, test_client, sample_export_data
    ):
        """Test selective component import."""
        # Mock app exists
        mock_app = Mock()
        mock_app.name = "Target App"
        mock_get_app.return_value = mock_app
        
        # Mock import service
        mock_summary = FullAppImportSummarySchema(
            app_name="Target App",
            app_id=1,
            total_components=2,
            components_imported={"ai_services": 1, "output_parsers": 1},
            components_skipped={
                "embedding_services": 1,
                "mcp_configs": 1,
                "silos": 1,
                "agents": 1,
            },
            total_warnings=[],
            total_errors=[],
            duration_seconds=0.3,
        )
        mock_import.return_value = mock_summary
        
        # Create file content
        export_json = sample_export_data.model_dump_json()
        
        # Make request with selective imports
        response = test_client.post(
            "/internal/apps/import-full?target_mode=existing_app&target_app_id=1&conflict_mode=fail&import_ai_services=true&import_embedding_services=false&import_output_parsers=true&import_mcp_configs=false&import_silos=false&import_agents=false",
            files={"file": ("export.json", export_json, "application/json")},
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        assert data["summary"]["total_components"] == 2
        assert data["summary"]["components_imported"]["ai_services"] == 1
        assert data["summary"]["components_skipped"]["embedding_services"] == 1
    
    def test_import_invalid_json(self, test_client):
        """Test import with invalid JSON returns 400."""
        # Create invalid JSON content
        invalid_json = "not valid json {{{"
        
        # Make request
        response = test_client.post(
            "/internal/apps/import-full?target_mode=existing_app&target_app_id=1",
            files={"file": ("export.json", invalid_json, "application/json")},
        )
        
        # Verify 400 response
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["detail"]
    
    def test_import_missing_target_app_id(self, test_client, sample_export_data):
        """Test import with existing_app mode but no target_app_id returns 400."""
        # Create file content
        export_json = sample_export_data.model_dump_json()
        
        # Make request without target_app_id
        response = test_client.post(
            "/internal/apps/import-full?target_mode=existing_app",
            files={"file": ("export.json", export_json, "application/json")},
        )
        
        # Verify 400 response
        assert response.status_code == 400
        assert "target_app_id" in response.json()["detail"].lower()
    
    @patch("services.full_app_import_service.FullAppImportService.import_full_app")
    @patch("repositories.app_repository.AppRepository.get_by_id")
    def test_import_conflict_modes(
        self, mock_get_app, mock_import, test_client, sample_export_data
    ):
        """Test different conflict modes."""
        # Mock app exists
        mock_app = Mock()
        mock_app.name = "Target App"
        mock_get_app.return_value = mock_app
        
        # Test each conflict mode
        for mode in ["fail", "rename", "override"]:
            # Mock import service
            mock_summary = FullAppImportSummarySchema(
                app_name="Target App",
                app_id=1,
                total_components=1,
                components_imported={"ai_services": 1},
                components_skipped={},
                total_warnings=[],
                total_errors=[],
                duration_seconds=0.1,
            )
            mock_import.return_value = mock_summary
            
            # Create file content
            export_json = sample_export_data.model_dump_json()
            
            # Make request
            response = test_client.post(
                f"/internal/apps/import-full?target_mode=existing_app&target_app_id=1&conflict_mode={mode}",
                files={"file": ("export.json", export_json, "application/json")},
            )
            
            # Verify response
            assert response.status_code == 200, f"Failed for conflict_mode={mode}"


# ==================== RUN TESTS ====================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
