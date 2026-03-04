"""
Integration tests for Embedding Service Export/Import with real PostgreSQL database.

These tests require:
- PostgreSQL running (docker compose up -d postgres)
- Database configured in .env
- Valid database connection

Usage:
    pytest backend/tests/test_embedding_export_import_integration.py -v -m integration

Mark as integration tests:
    @pytest.mark.integration
"""

import pytest
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session

# Add parent directory to path
backend_path = Path(__file__).parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from db.database import Base, get_db
from models.embedding_service import EmbeddingService, EmbeddingProvider
from models.app import App
from services.embedding_service_export_service import EmbeddingServiceExportService
from services.embedding_service_import_service import EmbeddingServiceImportService
from schemas.export_schemas import EmbeddingServiceExportFileSchema
from schemas.import_schemas import ConflictMode, ComponentType


# ==================== FIXTURES ====================


@pytest.fixture(scope="function")
def test_app(db_session: Session):
    """Create a test app for testing."""
    # Check if app exists
    app = (
        db_session.query(App)
        .filter(App.name == "Test App Embedding Export")
        .first()
    )

    if not app:
        app = App(name="Test App Embedding Export", slug="test-app-embedding-export")
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        created = True
    else:
        created = False

    yield app

    # Cleanup: Delete test embedding services first to avoid foreign key issues
    if created:
        db_session.query(EmbeddingService).filter(
            EmbeddingService.app_id == app.app_id
        ).delete()
        db_session.commit()

    # Cleanup only if we created it
    if created:
        db_session.delete(app)
        db_session.commit()


@pytest.fixture(scope="function")
def sample_embedding_service(db_session: Session, test_app: App):
    """Create a sample embedding service for testing."""
    service = EmbeddingService(
        app_id=test_app.app_id,
        name=f"Test OpenAI Embedding {datetime.now().timestamp()}",
        provider=EmbeddingProvider.OpenAI.value,  # Pass string value, not enum
        description="text-embedding-3-large",
        endpoint="https://api.openai.com/v1",
        api_key="sk-test-embedding-key-should-be-sanitized",
    )
    db_session.add(service)
    db_session.commit()
    db_session.refresh(service)

    yield service

    # Cleanup
    try:
        db_session.delete(service)
        db_session.commit()
    except Exception:
        db_session.rollback()


# ==================== INTEGRATION TESTS ====================


@pytest.mark.integration
class TestEmbeddingServiceExportIntegration:
    """Integration tests for Embedding Service export with real database."""

    def test_export_embedding_service_success(
        self, db_session: Session, sample_embedding_service: EmbeddingService
    ):
        """Test successful export of embedding service from database."""
        export_service = EmbeddingServiceExportService(db_session)

        export_data = export_service.export_embedding_service(
            sample_embedding_service.service_id,
            sample_embedding_service.app_id,
            user_id=1,
        )

        # Verify export structure
        assert isinstance(export_data, EmbeddingServiceExportFileSchema)
        assert export_data.metadata.export_version == "1.0.0"
        assert export_data.metadata.source_app_id == sample_embedding_service.app_id
        assert export_data.embedding_service.name == sample_embedding_service.name
        assert (
            export_data.embedding_service.provider
            == sample_embedding_service.provider
        )
        assert (
            export_data.embedding_service.model_name
            == sample_embedding_service.description
        )
        assert (
            export_data.embedding_service.endpoint
            == sample_embedding_service.endpoint
        )

    def test_export_sanitizes_api_key(
        self, db_session: Session, sample_embedding_service: EmbeddingService
    ):
        """Test that API key is sanitized in export (CRITICAL SECURITY TEST)."""
        export_service = EmbeddingServiceExportService(db_session)

        # Verify service has API key in database
        assert (
            sample_embedding_service.api_key
            == "sk-test-embedding-key-should-be-sanitized"
        )

        # Export
        export_data = export_service.export_embedding_service(
            sample_embedding_service.service_id,
            sample_embedding_service.app_id,
            user_id=1,
        )

        # CRITICAL: API key must be None in export
        assert export_data.embedding_service.api_key is None

    def test_export_nonexistent_service(self, db_session: Session, test_app: App):
        """Test export of non-existent service raises error."""
        export_service = EmbeddingServiceExportService(db_session)

        with pytest.raises(ValueError, match="not found"):
            export_service.export_embedding_service(
                service_id=99999, app_id=test_app.app_id, user_id=1
            )

    def test_export_wrong_app_id(
        self, db_session: Session, sample_embedding_service: EmbeddingService
    ):
        """Test export with wrong app_id raises error."""
        export_service = EmbeddingServiceExportService(db_session)

        with pytest.raises(ValueError, match="not found"):
            export_service.export_embedding_service(
                sample_embedding_service.service_id,
                app_id=99999,  # Wrong app ID
                user_id=1,
            )

    def test_export_to_json_file(
        self,
        db_session: Session,
        sample_embedding_service: EmbeddingService,
        tmp_path,
    ):
        """Test exporting to actual JSON file."""
        export_service = EmbeddingServiceExportService(db_session)

        export_data = export_service.export_embedding_service(
            sample_embedding_service.service_id,
            sample_embedding_service.app_id,
            user_id=1,
        )

        # Write to file
        export_file = tmp_path / "test_embedding_export.json"
        with open(export_file, "w") as f:
            json.dump(
                export_data.model_dump(mode="json"), f, indent=2, default=str
            )

        # Verify file exists and is valid JSON
        assert export_file.exists()

        with open(export_file, "r") as f:
            loaded_data = json.load(f)

        assert loaded_data["embedding_service"]["api_key"] is None
        assert (
            loaded_data["embedding_service"]["name"]
            == sample_embedding_service.name
        )


@pytest.mark.integration
class TestEmbeddingServiceImportIntegration:
    """Integration tests for Embedding Service import with real database."""

    def test_import_new_service_success(
        self, db_session: Session, test_app: App
    ):
        """Test importing a new embedding service successfully."""
        import_service = EmbeddingServiceImportService(db_session)

        # Create export data
        from schemas.export_schemas import (
            ExportMetadataSchema,
            ExportEmbeddingServiceSchema,
        )

        export_data = EmbeddingServiceExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=test_app.app_id,
            ),
            embedding_service=ExportEmbeddingServiceSchema(
                name=f"Imported Embedding Service {datetime.now().timestamp()}",
                api_key=None,
                provider=EmbeddingProvider.MistralAI,
                model_name="mistral-embed",
                endpoint="https://api.mistral.ai/v1",
                description=None,
            ),
        )

        # Import
        summary = import_service.import_embedding_service(
            export_data, test_app.app_id, conflict_mode=ConflictMode.FAIL
        )

        # Verify import summary
        assert summary.component_type == ComponentType.EMBEDDING_SERVICE
        assert summary.created is True
        assert (
            summary.component_name == export_data.embedding_service.name
        )
        assert summary.component_id > 0

        # Verify service exists in database
        imported_service = db_session.query(EmbeddingService).get(
            summary.component_id
        )
        assert imported_service is not None
        assert imported_service.name == export_data.embedding_service.name
        assert imported_service.provider == "MistralAI"  # Compare to string value
        assert imported_service.description == "mistral-embed"
        assert imported_service.api_key is None

        # Cleanup
        db_session.delete(imported_service)
        db_session.commit()

    def test_import_fail_on_conflict(
        self,
        db_session: Session,
        test_app: App,
        sample_embedding_service: EmbeddingService,
    ):
        """Test import fails when service name exists with FAIL mode."""
        import_service = EmbeddingServiceImportService(db_session)

        # Create export data with same name as existing service
        from schemas.export_schemas import (
            ExportMetadataSchema,
            ExportEmbeddingServiceSchema,
        )

        export_data = EmbeddingServiceExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=test_app.app_id,
            ),
            embedding_service=ExportEmbeddingServiceSchema(
                name=sample_embedding_service.name,  # Same name
                api_key=None,
                provider=EmbeddingProvider.OpenAI,
                model_name="text-embedding-3-large",
                endpoint="https://api.openai.com/v1",
                description=None,
            ),
        )

        # Import should fail
        with pytest.raises(ValueError, match="already exists"):
            import_service.import_embedding_service(
                export_data,
                test_app.app_id,
                conflict_mode=ConflictMode.FAIL,
            )

    def test_import_rename_on_conflict(
        self,
        db_session: Session,
        test_app: App,
        sample_embedding_service: EmbeddingService,
    ):
        """Test import renames service when conflict with RENAME mode."""
        import_service = EmbeddingServiceImportService(db_session)

        # Create export data with same name as existing service
        from schemas.export_schemas import (
            ExportMetadataSchema,
            ExportEmbeddingServiceSchema,
        )

        export_data = EmbeddingServiceExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=test_app.app_id,
            ),
            embedding_service=ExportEmbeddingServiceSchema(
                name=sample_embedding_service.name,  # Same name
                api_key=None,
                provider=EmbeddingProvider.Azure,
                model_name="text-embedding-ada-002",
                endpoint="https://azure.openai.com/v1",
                description=None,
            ),
        )

        # Import with RENAME mode
        summary = import_service.import_embedding_service(
            export_data,
            test_app.app_id,
            conflict_mode=ConflictMode.RENAME,
        )

        # Verify service was renamed
        assert summary.created is True
        assert summary.component_name != sample_embedding_service.name
        assert "(imported" in summary.component_name

        # Verify service exists in database with new name
        imported_service = db_session.query(EmbeddingService).get(
            summary.component_id
        )
        assert imported_service is not None
        assert imported_service.name != sample_embedding_service.name

        # Cleanup
        db_session.delete(imported_service)
        db_session.commit()

    def test_import_override_on_conflict(
        self,
        db_session: Session,
        test_app: App,
        sample_embedding_service: EmbeddingService,
    ):
        """Test import overrides existing service with OVERRIDE mode."""
        import_service = EmbeddingServiceImportService(db_session)

        # Store original ID
        original_id = sample_embedding_service.service_id

        # Create export data with same name but different config
        from schemas.export_schemas import (
            ExportMetadataSchema,
            ExportEmbeddingServiceSchema,
        )

        export_data = EmbeddingServiceExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=test_app.app_id,
            ),
            embedding_service=ExportEmbeddingServiceSchema(
                name=sample_embedding_service.name,  # Same name
                api_key=None,
                provider=EmbeddingProvider.Ollama,
                model_name="nomic-embed-text",  # Different model
                endpoint="http://localhost:11434",
                description=None,
            ),
        )

        # Import with OVERRIDE mode
        summary = import_service.import_embedding_service(
            export_data,
            test_app.app_id,
            conflict_mode=ConflictMode.OVERRIDE,
        )

        # Verify service was updated, not created
        assert summary.created is False
        assert summary.component_id == original_id
        assert summary.component_name == sample_embedding_service.name

        # Refresh service from database
        db_session.refresh(sample_embedding_service)

        # Verify configuration was updated
        assert sample_embedding_service.provider == "Ollama"  # Compare to string value
        assert sample_embedding_service.description == "nomic-embed-text"
        assert sample_embedding_service.endpoint == "http://localhost:11434"

        # Verify ID didn't change
        assert sample_embedding_service.service_id == original_id
