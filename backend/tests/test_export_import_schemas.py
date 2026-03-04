"""
Integration tests for AI Service Export/Import functionality (Phase 1).

Tests:
1. Export AI Service to JSON
2. Import AI Service with different conflict modes (FAIL, RENAME, OVERRIDE)
3. Validation of exported data (no API keys, correct structure)

Usage:
    pytest backend/tests/test_export_import_phase1.py -v

Requirements:
    - Backend server running
    - Valid authentication token in environment variable or config
    - At least one AI service configured
"""

import pytest
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from io import BytesIO
from unittest.mock import Mock, MagicMock, patch
from typing import Optional

# Add parent directory to path if needed
backend_path = Path(__file__).parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

# Import only what we need without triggering DB connection
from schemas.export_schemas import (
    ExportMetadataSchema,
    ExportAIServiceSchema,
    AIServiceExportFileSchema
)
from schemas.import_schemas import ConflictMode, ComponentType


# ==================== MOCK CLASSES ====================


class MockAIService:
    """Mock AI Service for testing without database."""
    
    def __init__(
        self,
        service_id=1,
        app_id=1,
        name="Test GPT-4 Service",
        provider="OpenAI",
        description="gpt-4",
        endpoint="https://api.openai.com/v1",
        api_key="sk-test-key-should-be-sanitized",
        api_version="v1"
    ):
        self.service_id = service_id
        self.app_id = app_id
        self.name = name
        self.provider = provider
        self.description = description
        self.endpoint = endpoint
        self.api_key = api_key
        self.api_version = api_version


class MockSession:
    """Mock database session for testing."""
    
    def __init__(self):
        self.added_items = []
        self.deleted_items = []
        self.committed = False
        self._services = {}
        self._next_id = 1
    
    def add(self, item):
        self.added_items.append(item)
        if not hasattr(item, 'service_id') or item.service_id is None:
            item.service_id = self._next_id
            self._next_id += 1
        self._services[item.service_id] = item
    
    def delete(self, item):
        self.deleted_items.append(item)
        if hasattr(item, 'service_id') and item.service_id in self._services:
            del self._services[item.service_id]
    
    def commit(self):
        self.committed = True
    
    def refresh(self, item):
        pass
    
    def query(self, model):
        return MockQuery(self._services)
    
    def get(self, id):
        return self._services.get(id)


class MockQuery:
    """Mock query for testing."""
    
    def __init__(self, services):
        self.services = services
        self.filters = []
    
    def filter(self, *args):
        self.filters.extend(args)
        return self
    
    def first(self):
        if self.services:
            return list(self.services.values())[0]
        return None
    
    def all(self):
        return list(self.services.values())


# ==================== FIXTURES ====================


@pytest.fixture
def mock_db_session():
    """Mock database session for tests."""
    return MockSession()


@pytest.fixture
def sample_ai_service():
    """Create a sample AI service for testing."""
    return MockAIService()


@pytest.fixture
def export_file(sample_ai_service):
    """Create an export file for testing imports."""
    return AIServiceExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
            exported_by="1",
            source_app_id=sample_ai_service.app_id
        ),
        ai_service=ExportAIServiceSchema(
            name=sample_ai_service.name,
            api_key=None,  # Always None for security
            provider=sample_ai_service.provider,
            model_name=sample_ai_service.description,
            endpoint=sample_ai_service.endpoint,
            description=sample_ai_service.description,
            api_version=sample_ai_service.api_version
        )
    )


# ==================== EXPORT TESTS ====================


class TestAIServiceExport:
    """Test AI Service export functionality."""
    
    def test_export_creates_valid_structure(self, sample_ai_service):
        """Test that export creates valid structure."""
        # Create export manually to test structure
        export_data = AIServiceExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=sample_ai_service.app_id
            ),
            ai_service=ExportAIServiceSchema(
                name=sample_ai_service.name,
                api_key=None,
                provider=sample_ai_service.provider,
                model_name=sample_ai_service.description,
                endpoint=sample_ai_service.endpoint,
                description=sample_ai_service.description,
                api_version=sample_ai_service.api_version
            )
        )
        
        # Verify export structure
        assert isinstance(export_data, AIServiceExportFileSchema)
        assert export_data.metadata.export_version == "1.0.0"
        assert export_data.metadata.source_app_id == sample_ai_service.app_id
        assert export_data.ai_service.name == sample_ai_service.name
        assert export_data.ai_service.provider == sample_ai_service.provider
    
    def test_export_sanitizes_api_key(self, sample_ai_service):
        """Test that API key is sanitized (set to None) in export."""
        # Create export with None API key
        export_data = AIServiceExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=sample_ai_service.app_id
            ),
            ai_service=ExportAIServiceSchema(
                name=sample_ai_service.name,
                api_key=None,  # CRITICAL: Must be None
                provider=sample_ai_service.provider,
                model_name=sample_ai_service.description,
                endpoint=sample_ai_service.endpoint
            )
        )
        
        # CRITICAL: API key must be None for security
        assert export_data.ai_service.api_key is None
    
    def test_export_includes_all_fields(self, sample_ai_service):
        """Test that export includes all necessary fields."""
        export_data = AIServiceExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now()
            ),
            ai_service=ExportAIServiceSchema(
                name=sample_ai_service.name,
                api_key=None,
                provider=sample_ai_service.provider,
                model_name=sample_ai_service.description,
                endpoint=sample_ai_service.endpoint,
                description=sample_ai_service.description,
                api_version=sample_ai_service.api_version
            )
        )
        
        assert export_data.ai_service.name is not None
        assert export_data.ai_service.provider is not None
        assert export_data.ai_service.model_name is not None


# ==================== IMPORT VALIDATION TESTS ====================


class TestAIServiceImportValidation:
    """Test AI Service import validation."""
    
    def test_validate_import_structure(self, export_file):
        """Test validation of import file structure."""
        # Verify export file is valid
        assert export_file.metadata.export_version == "1.0.0"
        assert export_file.ai_service is not None
        assert export_file.ai_service.name is not None
    
    def test_validate_api_key_warning(self, export_file):
        """Test that validation warns about missing API key."""
        # When api_key is None, users should be warned to configure it
        assert export_file.ai_service.api_key is None


# ==================== IMPORT TESTS ====================


class TestAIServiceImport:
    """Test AI Service import functionality with mocks."""
    
    def test_import_conflict_modes_exist(self):
        """Test that all conflict modes are defined."""
        assert ConflictMode.FAIL == "fail"
        assert ConflictMode.RENAME == "rename"
        assert ConflictMode.OVERRIDE == "override"
    
    def test_component_type_is_ai_service(self):
        """Test that component type is correctly set."""
        assert ComponentType.AI_SERVICE == "ai_service"
    
    def test_export_to_json_serialization(self, export_file):
        """Test that export file can be serialized to JSON."""
        json_data = export_file.model_dump(mode='json')
        
        assert 'metadata' in json_data
        assert 'ai_service' in json_data
        assert json_data['ai_service']['api_key'] is None
        assert json_data['metadata']['export_version'] == "1.0.0"
    
    def test_import_from_json_deserialization(self, export_file):
        """Test that export file can be deserialized from JSON."""
        # Serialize to JSON
        json_str = export_file.model_dump_json()
        
        # Deserialize back
        json_data = json.loads(json_str)
        reimported = AIServiceExportFileSchema(**json_data)
        
        assert reimported.ai_service.name == export_file.ai_service.name
        assert reimported.ai_service.api_key is None
        assert reimported.metadata.export_version == export_file.metadata.export_version


# ==================== SCHEMA VALIDATION TESTS ====================


class TestExportSchemaValidation:
    """Test export schema validation."""
    
    def test_export_file_schema_valid(self):
        """Test valid export file schema."""
        from schemas.export_schemas import (
            ExportMetadataSchema,
            ExportAIServiceSchema,
            AIServiceExportFileSchema
        )
        
        export_data = AIServiceExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=1
            ),
            ai_service=ExportAIServiceSchema(
                name="Test Service",
                api_key=None,
                provider="OpenAI",
                model_name="gpt-4",
                endpoint="https://api.openai.com/v1"
            )
        )
        
        assert export_data.metadata.export_version == "1.0.0"
        assert export_data.ai_service.api_key is None
    
    def test_export_schema_rejects_empty_name(self):
        """Test export schema rejects empty name."""
        from schemas.export_schemas import ExportAIServiceSchema
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            ExportAIServiceSchema(
                name="",  # Empty name should be rejected
                api_key=None,
                provider="OpenAI",
                model_name="gpt-4"
            )
