"""
API tests for AI Service Export/Import REST endpoints.

These tests verify:
- HTTP endpoints and status codes
- Request/response formats
- Authentication and authorization
- Error handling at API level

Usage:
    pytest backend/tests/test_export_import_api.py -v
"""

import pytest
import json
import io
import sys
from pathlib import Path
from datetime import datetime
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.orm import Session

# Add backend directory to path
backend_path = Path(__file__).parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from schemas.export_schemas import (
    AIServiceExportFileSchema,
    ExportAIServiceSchema,
    ExportMetadataSchema
)
from schemas.import_schemas import ConflictMode, ImportSummarySchema, ComponentType


# ==================== FIXTURES ====================


@pytest.fixture
def test_client():
    """Create FastAPI test client with authentication bypassed."""
    from main import app
    from fastapi import Depends
    from routers.internal import ai_services
    from unittest.mock import Mock
    
    # Create mock auth context
    mock_auth = Mock()
    mock_auth.user_id = 1
    mock_auth.username = "test_user"
    mock_auth.email = "test@example.com"
    
    # Override dependencies to bypass authentication
    app.dependency_overrides[ai_services.get_current_user_oauth] = lambda: mock_auth
    app.dependency_overrides[ai_services.require_min_role] = lambda x: lambda: mock_auth
    
    client = TestClient(app)
    yield client
    
    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
def mock_auth_context():
    """Mock authentication context."""
    mock_ctx = Mock()
    mock_ctx.user_id = 1
    mock_ctx.username = "test_user"
    return mock_ctx


@pytest.fixture
def sample_export_data():
    """Sample export data for testing."""
    return AIServiceExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            component_type="ai_service",
            exported_at=datetime.now().isoformat(),
            exported_by="test_user"
        ),
        ai_service=ExportAIServiceSchema(
            provider="OpenAI",
            name="Test GPT-4 Service",
            model_name="gpt-4",
            base_url="https://api.openai.com/v1",
            api_version="v1",
            api_key=None,
            description=None
        )
    )


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    mock_session = MagicMock(spec=Session)
    return mock_session


# ==================== EXPORT ENDPOINT TESTS ====================


class TestExportEndpoint:
    """Test AI Service export endpoint."""
    
    @patch("routers.internal.ai_services.get_current_user_oauth")
    @patch("routers.internal.ai_services.require_min_role")
    @patch("routers.internal.ai_services.get_db")
    @patch("routers.internal.ai_services.AIServiceExportService")
    def test_export_success(
        self,
        mock_export_service_class,
        mock_get_db,
        mock_require_role,
        mock_get_user,
        test_client,
        mock_auth_context,
        sample_export_data
    ):
        """Test successful export returns JSON with correct headers."""
        # Setup mocks
        mock_get_user.return_value = mock_auth_context
        mock_require_role.return_value = Mock()
        mock_get_db.return_value = Mock()
        
        mock_export_service = Mock()
        mock_export_service.export_ai_service.return_value = sample_export_data
        mock_export_service_class.return_value = mock_export_service
        
        # Make request
        response = test_client.post(
            "/internal/ai-services/123/export",
            params={"app_id": 1}
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        assert "application/json" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        assert "Test_GPT-4_Service_ai_service.json" in response.headers["content-disposition"]
        
        # Verify response data
        data = response.json()
        assert data["metadata"]["export_version"] == "1.0.0"
        assert data["ai_service"]["name"] == "Test GPT-4 Service"
        assert data["ai_service"]["api_key"] is None
    
    @patch("routers.internal.ai_services.get_current_user_oauth")
    @patch("routers.internal.ai_services.require_min_role")
    @patch("routers.internal.ai_services.get_db")
    @patch("routers.internal.ai_services.AIServiceExportService")
    def test_export_not_found(
        self,
        mock_export_service_class,
        mock_get_db,
        mock_require_role,
        mock_get_user,
        test_client,
        mock_auth_context
    ):
        """Test export with non-existent service returns 404."""
        # Setup mocks
        mock_get_user.return_value = mock_auth_context
        mock_require_role.return_value = Mock()
        mock_get_db.return_value = Mock()
        
        mock_export_service = Mock()
        mock_export_service.export_ai_service.side_effect = ValueError("AI Service not found")
        mock_export_service_class.return_value = mock_export_service
        
        # Make request
        response = test_client.post(
            "/internal/ai-services/999/export",
            params={"app_id": 1}
        )
        
        # Assertions
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()
    
    @patch("routers.internal.ai_services.get_current_user_oauth")
    @patch("routers.internal.ai_services.require_min_role")
    @patch("routers.internal.ai_services.get_db")
    @patch("routers.internal.ai_services.AIServiceExportService")
    def test_export_wrong_app(
        self,
        mock_export_service_class,
        mock_get_db,
        mock_require_role,
        mock_get_user,
        test_client,
        mock_auth_context
    ):
        """Test export with wrong app_id returns 400."""
        # Setup mocks
        mock_get_user.return_value = mock_auth_context
        mock_require_role.return_value = Mock()
        mock_get_db.return_value = Mock()
        
        mock_export_service = Mock()
        mock_export_service.export_ai_service.side_effect = ValueError(
            "Service does not belong to app"
        )
        mock_export_service_class.return_value = mock_export_service
        
        # Make request
        response = test_client.post(
            "/internal/ai-services/123/export",
            params={"app_id": 999}
        )
        
        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    @patch("routers.internal.ai_services.get_current_user_oauth")
    @patch("routers.internal.ai_services.require_min_role")
    @patch("routers.internal.ai_services.get_db")
    @patch("routers.internal.ai_services.AIServiceExportService")
    def test_export_server_error(
        self,
        mock_export_service_class,
        mock_get_db,
        mock_require_role,
        mock_get_user,
        test_client,
        mock_auth_context
    ):
        """Test export with unexpected error returns 500."""
        # Setup mocks
        mock_get_user.return_value = mock_auth_context
        mock_require_role.return_value = Mock()
        mock_get_db.return_value = Mock()
        
        mock_export_service = Mock()
        mock_export_service.export_ai_service.side_effect = Exception("Database error")
        mock_export_service_class.return_value = mock_export_service
        
        # Make request
        response = test_client.post(
            "/internal/ai-services/123/export",
            params={"app_id": 1}
        )
        
        # Assertions
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Export failed" in response.json()["detail"]


# ==================== IMPORT ENDPOINT TESTS ====================


class TestImportEndpoint:
    """Test AI Service import endpoint."""
    
    @patch("routers.internal.ai_services.get_current_user_oauth")
    @patch("routers.internal.ai_services.require_min_role")
    @patch("routers.internal.ai_services.get_db")
    @patch("routers.internal.ai_services.AIServiceImportService")
    def test_import_success(
        self,
        mock_import_service_class,
        mock_get_db,
        mock_require_role,
        mock_get_user,
        test_client,
        mock_auth_context,
        sample_export_data
    ):
        """Test successful import returns 201 with summary."""
        # Setup mocks
        mock_get_user.return_value = mock_auth_context
        mock_require_role.return_value = Mock()
        mock_get_db.return_value = Mock()
        
        mock_import_service = Mock()
        mock_import_service.import_ai_service.return_value = ImportSummarySchema(
            component_type=ComponentType.AI_SERVICE,
            component_id=123,
            component_name="Test GPT-4 Service",
            mode=ConflictMode.FAIL,
            created=True,
            dependencies_created=[],
            warnings=[],
            next_steps=["Configure API key for the imported AI Service"]
        )
        mock_import_service_class.return_value = mock_import_service
        
        # Create file
        file_content = sample_export_data.model_dump_json()
        file = ("test_import.json", io.BytesIO(file_content.encode()), "application/json")
        
        # Make request
        response = test_client.post(
            "/internal/ai-services/import",
            params={"app_id": 1, "conflict_mode": "fail"},
            files={"file": file}
        )
        
        # Assertions
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True
        assert "imported successfully" in data["message"]
        assert data["summary"]["component_type"] == "ai_service"
        assert data["summary"]["created"] is True
        assert data["summary"]["component_id"] == 123
    
    @patch("routers.internal.ai_services.get_current_user_oauth")
    @patch("routers.internal.ai_services.require_min_role")
    @patch("routers.internal.ai_services.get_db")
    @patch("routers.internal.ai_services.AIServiceImportService")
    def test_import_with_conflict_fail_mode(
        self,
        mock_import_service_class,
        mock_get_db,
        mock_require_role,
        mock_get_user,
        test_client,
        mock_auth_context,
        sample_export_data
    ):
        """Test import with FAIL mode when service exists returns 400."""
        # Setup mocks
        mock_get_user.return_value = mock_auth_context
        mock_require_role.return_value = Mock()
        mock_get_db.return_value = Mock()
        
        mock_import_service = Mock()
        mock_import_service.import_ai_service.side_effect = ValueError(
            "Service 'Test GPT-4 Service' already exists"
        )
        mock_import_service_class.return_value = mock_import_service
        
        # Create file
        file_content = sample_export_data.model_dump_json()
        file = ("test_import.json", io.BytesIO(file_content.encode()), "application/json")
        
        # Make request
        response = test_client.post(
            "/internal/ai-services/import",
            params={"app_id": 1, "conflict_mode": "fail"},
            files={"file": file}
        )
        
        # Assertions
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "already exists" in response.json()["detail"]
    
    @patch("routers.internal.ai_services.get_current_user_oauth")
    @patch("routers.internal.ai_services.require_min_role")
    @patch("routers.internal.ai_services.get_db")
    @patch("routers.internal.ai_services.AIServiceImportService")
    def test_import_with_rename_mode(
        self,
        mock_import_service_class,
        mock_get_db,
        mock_require_role,
        mock_get_user,
        test_client,
        mock_auth_context,
        sample_export_data
    ):
        """Test import with RENAME mode auto-generates new name."""
        # Setup mocks
        mock_get_user.return_value = mock_auth_context
        mock_require_role.return_value = Mock()
        mock_get_db.return_value = Mock()
        
        mock_import_service = Mock()
        mock_import_service.import_ai_service.return_value = ImportSummarySchema(
            component_type=ComponentType.AI_SERVICE,
            component_id=124,
            component_name="Test GPT-4 Service (imported 2026-02-09)",
            mode=ConflictMode.RENAME,
            created=True,
            dependencies_created=[],
            warnings=[],
            next_steps=["Configure API key for the imported AI Service"]
        )
        mock_import_service_class.return_value = mock_import_service
        
        # Create file
        file_content = sample_export_data.model_dump_json()
        file = ("test_import.json", io.BytesIO(file_content.encode()), "application/json")
        
        # Make request
        response = test_client.post(
            "/internal/ai-services/import",
            params={"app_id": 1, "conflict_mode": "rename"},
            files={"file": file}
        )
        
        # Assertions
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True
        assert "imported" in data["summary"]["component_name"].lower()
    
    @patch("routers.internal.ai_services.get_current_user_oauth")
    @patch("routers.internal.ai_services.require_min_role")
    @patch("routers.internal.ai_services.get_db")
    @patch("routers.internal.ai_services.AIServiceImportService")
    def test_import_with_custom_name(
        self,
        mock_import_service_class,
        mock_get_db,
        mock_require_role,
        mock_get_user,
        test_client,
        mock_auth_context,
        sample_export_data
    ):
        """Test import with custom name."""
        # Setup mocks
        mock_get_user.return_value = mock_auth_context
        mock_require_role.return_value = Mock()
        mock_get_db.return_value = Mock()
        
        mock_import_service = Mock()
        mock_import_service.import_ai_service.return_value = ImportSummarySchema(
            component_type=ComponentType.AI_SERVICE,
            component_id=125,
            component_name="Custom Import Name",
            mode=ConflictMode.RENAME,
            created=True,
            dependencies_created=[],
            warnings=[],
            next_steps=["Configure API key for the imported AI Service"]
        )
        mock_import_service_class.return_value = mock_import_service
        
        # Create file
        file_content = sample_export_data.model_dump_json()
        file = ("test_import.json", io.BytesIO(file_content.encode()), "application/json")
        
        # Make request
        response = test_client.post(
            "/internal/ai-services/import",
            params={
                "app_id": 1,
                "conflict_mode": "rename",
                "new_name": "Custom Import Name"
            },
            files={"file": file}
        )
        
        # Assertions
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["summary"]["component_name"] == "Custom Import Name"
    
    @patch("routers.internal.ai_services.get_current_user_oauth")
    @patch("routers.internal.ai_services.require_min_role")
    @patch("routers.internal.ai_services.get_db")
    @patch("routers.internal.ai_services.AIServiceImportService")
    def test_import_with_override_mode(
        self,
        mock_import_service_class,
        mock_get_db,
        mock_require_role,
        mock_get_user,
        test_client,
        mock_auth_context,
        sample_export_data
    ):
        """Test import with OVERRIDE mode updates existing service."""
        # Setup mocks
        mock_get_user.return_value = mock_auth_context
        mock_require_role.return_value = Mock()
        mock_get_db.return_value = Mock()
        
        mock_import_service = Mock()
        mock_import_service.import_ai_service.return_value = ImportSummarySchema(
            component_type=ComponentType.AI_SERVICE,
            component_id=123,
            component_name="Test GPT-4 Service",
            mode=ConflictMode.OVERRIDE,
            created=False,
            dependencies_created=[],
            warnings=["Existing API key preserved"],
            next_steps=[]
        )
        mock_import_service_class.return_value = mock_import_service
        
        # Create file
        file_content = sample_export_data.model_dump_json()
        file = ("test_import.json", io.BytesIO(file_content.encode()), "application/json")
        
        # Make request
        response = test_client.post(
            "/internal/ai-services/import",
            params={"app_id": 1, "conflict_mode": "override"},
            files={"file": file}
        )
        
        # Assertions
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["summary"]["created"] is False
        assert any("API key" in w for w in data["summary"]["warnings"])
    
    @patch("routers.internal.ai_services.get_current_user_oauth")
    @patch("routers.internal.ai_services.require_min_role")
    @patch("routers.internal.ai_services.get_db")
    def test_import_invalid_json(
        self,
        mock_get_db,
        mock_require_role,
        mock_get_user,
        test_client,
        mock_auth_context
    ):
        """Test import with invalid JSON returns 400."""
        # Setup mocks
        mock_get_user.return_value = mock_auth_context
        mock_require_role.return_value = Mock()
        mock_get_db.return_value = Mock()
        
        # Create invalid file
        file = ("test_import.json", io.BytesIO(b"not valid json"), "application/json")
        
        # Make request
        response = test_client.post(
            "/internal/ai-services/import",
            params={"app_id": 1, "conflict_mode": "fail"},
            files={"file": file}
        )
        
        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    @patch("routers.internal.ai_services.get_current_user_oauth")
    @patch("routers.internal.ai_services.require_min_role")
    @patch("routers.internal.ai_services.get_db")
    def test_import_missing_fields(
        self,
        mock_get_db,
        mock_require_role,
        mock_get_user,
        test_client,
        mock_auth_context
    ):
        """Test import with missing required fields returns 400."""
        # Setup mocks
        mock_get_user.return_value = mock_auth_context
        mock_require_role.return_value = Mock()
        mock_get_db.return_value = Mock()
        
        # Create incomplete data
        incomplete_data = {
            "metadata": {"export_version": "1.0.0"},
            # Missing ai_service
        }
        file_content = json.dumps(incomplete_data)
        file = ("test_import.json", io.BytesIO(file_content.encode()), "application/json")
        
        # Make request
        response = test_client.post(
            "/internal/ai-services/import",
            params={"app_id": 1, "conflict_mode": "fail"},
            files={"file": file}
        )
        
        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    @patch("routers.internal.ai_services.get_current_user_oauth")
    @patch("routers.internal.ai_services.require_min_role")
    @patch("routers.internal.ai_services.get_db")
    @patch("routers.internal.ai_services.AIServiceImportService")
    def test_import_server_error(
        self,
        mock_import_service_class,
        mock_get_db,
        mock_require_role,
        mock_get_user,
        test_client,
        mock_auth_context,
        sample_export_data
    ):
        """Test import with unexpected error returns 500."""
        # Setup mocks
        mock_get_user.return_value = mock_auth_context
        mock_require_role.return_value = Mock()
        mock_get_db.return_value = Mock()
        
        mock_import_service = Mock()
        mock_import_service.import_ai_service.side_effect = Exception("Database error")
        mock_import_service_class.return_value = mock_import_service
        
        # Create file
        file_content = sample_export_data.model_dump_json()
        file = ("test_import.json", io.BytesIO(file_content.encode()), "application/json")
        
        # Make request
        response = test_client.post(
            "/internal/ai-services/import",
            params={"app_id": 1, "conflict_mode": "fail"},
            files={"file": file}
        )
        
        # Assertions
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Import failed" in response.json()["detail"]


# ==================== INTEGRATION TESTS ====================


class TestExportImportAPIRoundtrip:
    """Test complete export-import flow via API."""
    
    @patch("routers.internal.ai_services.get_current_user_oauth")
    @patch("routers.internal.ai_services.require_min_role")
    @patch("routers.internal.ai_services.get_db")
    @patch("routers.internal.ai_services.AIServiceExportService")
    @patch("routers.internal.ai_services.AIServiceImportService")
    def test_roundtrip_export_then_import(
        self,
        mock_import_service_class,
        mock_export_service_class,
        mock_get_db,
        mock_require_role,
        mock_get_user,
        test_client,
        mock_auth_context,
        sample_export_data
    ):
        """Test exporting a service and then importing it back."""
        # Setup mocks
        mock_get_user.return_value = mock_auth_context
        mock_require_role.return_value = Mock()
        mock_get_db.return_value = Mock()
        
        # Setup export
        mock_export_service = Mock()
        mock_export_service.export_ai_service.return_value = sample_export_data
        mock_export_service_class.return_value = mock_export_service
        
        # Setup import
        mock_import_service = Mock()
        mock_import_service.import_ai_service.return_value = ImportSummarySchema(
            component_type=ComponentType.AI_SERVICE,
            component_id=999,
            component_name="Test GPT-4 Service (imported)",
            mode=ConflictMode.RENAME,
            created=True,
            dependencies_created=[],
            warnings=[],
            next_steps=["Configure API key for the imported AI Service"]
        )
        mock_import_service_class.return_value = mock_import_service
        
        # Step 1: Export
        export_response = test_client.post(
            "/internal/ai-services/123/export",
            params={"app_id": 1}
        )
        assert export_response.status_code == status.HTTP_200_OK
        export_data = export_response.json()
        
        # Step 2: Import the exported data
        file_content = json.dumps(export_data)
        file = ("export.json", io.BytesIO(file_content.encode()), "application/json")
        
        import_response = test_client.post(
            "/internal/ai-services/import",
            params={"app_id": 1, "conflict_mode": "rename"},
            files={"file": file}
        )
        
        # Assertions
        assert import_response.status_code == status.HTTP_201_CREATED
        import_data = import_response.json()
        assert import_data["success"] is True
        assert import_data["summary"]["created"] is True
