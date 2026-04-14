"""
Schema validation tests for Embedding Service Export/Import (Phase 2).

Tests:
1. ExportEmbeddingServiceSchema validation
2. EmbeddingServiceExportFileSchema structure
3. Provider enum validation
4. API key sanitization in schemas

Usage:
    pytest backend/tests/test_embedding_export_import_schemas.py -v
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from schemas.export_schemas import (
    ExportMetadataSchema,
    ExportEmbeddingServiceSchema,
    EmbeddingServiceExportFileSchema
)
from schemas.import_schemas import ConflictMode, ComponentType
from models.embedding_service import EmbeddingProvider


class TestExportEmbeddingServiceSchema:
    """Test ExportEmbeddingServiceSchema validation."""
    
    def test_valid_embedding_service_schema(self):
        """Test creating valid embedding service export schema."""
        schema = ExportEmbeddingServiceSchema(
            name="Test Embedding Service",
            api_key=None,
            provider=EmbeddingProvider.OpenAI,
            model_name="text-embedding-3-large",
            endpoint="https://api.openai.com/v1",
            description=None
        )
        
        assert schema.name == "Test Embedding Service"
        assert schema.api_key is None
        assert schema.provider == "OpenAI"  # Stored as string in schema
        assert schema.model_name == "text-embedding-3-large"
        assert schema.endpoint == "https://api.openai.com/v1"
    
    def test_api_key_must_be_none(self):
        """Test that API key must be None in export schema."""
        # This should work - API key is None
        schema = ExportEmbeddingServiceSchema(
            name="Test Service",
            api_key=None,
            provider=EmbeddingProvider.MistralAI,
            model_name="mistral-embed",
            endpoint="https://api.mistral.ai/v1",
            description=None
        )
        assert schema.api_key is None
    
    def test_provider_validation(self):
        """Test provider enum validation."""
        valid_providers = [
            EmbeddingProvider.OpenAI,
            EmbeddingProvider.MistralAI,
            EmbeddingProvider.Ollama,
            EmbeddingProvider.Azure,
            EmbeddingProvider.Custom
        ]
        
        for provider in valid_providers:
            schema = ExportEmbeddingServiceSchema(
                name=f"Test {provider} Service",
                api_key=None,
                provider=provider,
                model_name="test-model",
                endpoint="https://api.example.com",
                description=None
            )
            assert schema.provider == provider.value  # Compare to enum string value
    
    def test_required_fields(self):
        """Test that required fields are validated."""
        # Missing name
        with pytest.raises(ValidationError):
            ExportEmbeddingServiceSchema(
                api_key=None,
                provider=EmbeddingProvider.OpenAI,
                model_name="text-embedding-3-large",
                endpoint="https://api.openai.com/v1"
            )
        
        # Missing provider
        with pytest.raises(ValidationError):
            ExportEmbeddingServiceSchema(
                name="Test Service",
                api_key=None,
                model_name="text-embedding-3-large",
                endpoint="https://api.openai.com/v1"
            )


class TestEmbeddingServiceExportFileSchema:
    """Test complete export file schema."""
    
    def test_valid_export_file(self):
        """Test creating valid complete export file."""
        export_file = EmbeddingServiceExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=1
            ),
            embedding_service=ExportEmbeddingServiceSchema(
                name="Test Embedding Service",
                api_key=None,
                provider=EmbeddingProvider.OpenAI,
                model_name="text-embedding-3-large",
                endpoint="https://api.openai.com/v1",
                description=None
            )
        )
        
        assert export_file.metadata.export_version == "1.0.0"
        assert export_file.metadata.source_app_id == 1
        assert export_file.embedding_service.name == "Test Embedding Service"
        assert export_file.embedding_service.api_key is None
    
    def test_export_file_serialization(self):
        """Test that export file can be serialized to JSON."""
        export_file = EmbeddingServiceExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=1
            ),
            embedding_service=ExportEmbeddingServiceSchema(
                name="Test Service",
                api_key=None,
                provider=EmbeddingProvider.Ollama,
                model_name="nomic-embed-text",
                endpoint="http://localhost:11434",
                description=None
            )
        )
        
        # Serialize to dict (JSON-compatible)
        data = export_file.model_dump(mode='json')
        
        assert isinstance(data, dict)
        assert 'metadata' in data
        assert 'embedding_service' in data
        assert data['embedding_service']['api_key'] is None
        assert data['embedding_service']['provider'] == 'Ollama'


class TestConflictModeEnum:
    """Test ConflictMode enum for import."""
    
    def test_conflict_mode_values(self):
        """Test all conflict mode values."""
        assert ConflictMode.FAIL == "fail"
        assert ConflictMode.RENAME == "rename"
        assert ConflictMode.OVERRIDE == "override"
    
    def test_conflict_mode_from_string(self):
        """Test creating conflict mode from string."""
        assert ConflictMode("fail") == ConflictMode.FAIL
        assert ConflictMode("rename") == ConflictMode.RENAME
        assert ConflictMode("override") == ConflictMode.OVERRIDE


class TestComponentType:
    """Test ComponentType enum."""
    
    def test_embedding_service_component_type(self):
        """Test embedding service component type."""
        assert hasattr(ComponentType, 'EMBEDDING_SERVICE')
        assert ComponentType.EMBEDDING_SERVICE == "embedding_service"
