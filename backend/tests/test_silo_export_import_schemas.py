"""Tests for Silo export/import schemas."""

import pytest
from pydantic import ValidationError
from datetime import datetime
from schemas.export_schemas import (
    ExportSiloSchema,
    SiloExportFileSchema,
    ExportMetadataSchema,
)


def test_export_silo_schema_valid():
    """Test valid ExportSiloSchema."""
    schema = ExportSiloSchema(
        name="Test Silo",
        type="CUSTOM",
        vector_db_type="PGVECTOR",
        embedding_service_name="OpenAI Embeddings",
        metadata_definition_name="Document Parser",
        fixed_metadata=True,
        description="Test silo description",
    )
    
    assert schema.name == "Test Silo"
    assert schema.type == "CUSTOM"
    assert schema.vector_db_type == "PGVECTOR"
    assert schema.embedding_service_name == "OpenAI Embeddings"
    assert schema.metadata_definition_name == "Document Parser"
    assert schema.fixed_metadata is True
    assert schema.description == "Test silo description"


def test_export_silo_schema_minimal():
    """Test ExportSiloSchema with minimal fields."""
    schema = ExportSiloSchema(
        name="Minimal Silo",
        type="REPO",
        vector_db_type="QDRANT",
    )
    
    assert schema.name == "Minimal Silo"
    assert schema.type == "REPO"
    assert schema.vector_db_type == "QDRANT"
    assert schema.embedding_service_name is None
    assert schema.metadata_definition_name is None
    assert schema.fixed_metadata is False  # Default value
    assert schema.description is None


def test_export_silo_schema_name_validation():
    """Test ExportSiloSchema name validation."""
    # Empty name should fail
    with pytest.raises(ValidationError) as exc_info:
        ExportSiloSchema(
            name="",
            type="CUSTOM",
            vector_db_type="PGVECTOR",
        )
    assert "name" in str(exc_info.value)
    
    # Name too long (>255 chars) should fail
    with pytest.raises(ValidationError) as exc_info:
        ExportSiloSchema(
            name="A" * 256,
            type="CUSTOM",
            vector_db_type="PGVECTOR",
        )
    assert "name" in str(exc_info.value)


def test_export_silo_schema_optional_dependencies():
    """Test ExportSiloSchema with optional dependencies."""
    # With embedding service only
    schema = ExportSiloSchema(
        name="Silo 1",
        type="DOMAIN",
        vector_db_type="PGVECTOR",
        embedding_service_name="Mistral Embeddings",
    )
    assert schema.embedding_service_name == "Mistral Embeddings"
    assert schema.metadata_definition_name is None
    
    # With output parser only
    schema = ExportSiloSchema(
        name="Silo 2",
        type="CUSTOM",
        vector_db_type="QDRANT",
        metadata_definition_name="JSON Parser",
    )
    assert schema.embedding_service_name is None
    assert schema.metadata_definition_name == "JSON Parser"


def test_silo_export_file_schema_complete():
    """Test SiloExportFileSchema with all dependencies."""
    from schemas.export_schemas import (
        ExportEmbeddingServiceSchema,
        ExportOutputParserSchema,
    )
    
    export_file = SiloExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
            exported_by_user_id=1,
            source_app_id=1,
        ),
        silo=ExportSiloSchema(
            name="Complete Silo",
            type="CUSTOM",
            vector_db_type="PGVECTOR",
            embedding_service_name="OpenAI",
            metadata_definition_name="Parser",
            fixed_metadata=True,
        ),
        embedding_service=ExportEmbeddingServiceSchema(
            name="OpenAI",
            provider="OpenAI",
            model_name="text-embedding-3-small",
            api_key=None,
            endpoint="https://api.openai.com/v1",
        ),
        output_parser=ExportOutputParserSchema(
            name="Parser",
            description="Test parser",
            fields=[],
        ),
    )
    
    assert export_file.silo.name == "Complete Silo"
    assert export_file.embedding_service is not None
    assert export_file.embedding_service.name == "OpenAI"
    assert export_file.output_parser is not None
    assert export_file.output_parser.name == "Parser"


def test_silo_export_file_schema_without_dependencies():
    """Test SiloExportFileSchema without bundled dependencies."""
    export_file = SiloExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
        ),
        silo=ExportSiloSchema(
            name="Standalone Silo",
            type="REPO",
            vector_db_type="QDRANT",
            embedding_service_name="External Service",
        ),
    )
    
    assert export_file.silo.name == "Standalone Silo"
    assert export_file.silo.embedding_service_name == "External Service"
    assert export_file.embedding_service is None
    assert export_file.output_parser is None


def test_export_silo_schema_serialization():
    """Test ExportSiloSchema serialization to JSON."""
    schema = ExportSiloSchema(
        name="JSON Silo",
        type="CUSTOM",
        vector_db_type="PGVECTOR",
        embedding_service_name="Test Service",
        fixed_metadata=True,
        description="Test description",
    )
    
    # Test model_dump
    data = schema.model_dump()
    assert data["name"] == "JSON Silo"
    assert data["type"] == "CUSTOM"
    assert data["fixed_metadata"] is True
    
    # Test JSON serialization
    json_str = schema.model_dump_json()
    assert "JSON Silo" in json_str
    assert "CUSTOM" in json_str


def test_export_silo_schema_no_collection_name():
    """Test that collection_name is NOT in ExportSiloSchema (it's auto-generated)."""
    schema = ExportSiloSchema(
        name="Test",
        type="CUSTOM",
        vector_db_type="PGVECTOR",
    )
    
    # Verify collection_name field doesn't exist
    assert not hasattr(schema, "collection_name")
    
    # Verify it's not in the serialized data
    data = schema.model_dump()
    assert "collection_name" not in data


def test_export_silo_schema_fixed_metadata_default():
    """Test fixed_metadata defaults to False."""
    schema = ExportSiloSchema(
        name="Test",
        type="CUSTOM",
        vector_db_type="PGVECTOR",
    )
    
    assert schema.fixed_metadata is False


def test_silo_export_file_schema_metadata_required():
    """Test that metadata is required in SiloExportFileSchema."""
    with pytest.raises(ValidationError) as exc_info:
        SiloExportFileSchema(
            silo=ExportSiloSchema(
                name="Test",
                type="CUSTOM",
                vector_db_type="PGVECTOR",
            ),
        )
    assert "metadata" in str(exc_info.value)


def test_export_silo_schema_vector_db_types():
    """Test different vector_db_type values."""
    for db_type in ["PGVECTOR", "QDRANT", "MILVUS", "PINECONE"]:
        schema = ExportSiloSchema(
            name=f"Silo {db_type}",
            type="CUSTOM",
            vector_db_type=db_type,
        )
        assert schema.vector_db_type == db_type
