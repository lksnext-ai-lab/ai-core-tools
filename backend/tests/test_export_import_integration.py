"""
Integration tests for AI Service Export/Import with real PostgreSQL database.

These tests require:
- PostgreSQL running (docker compose up -d postgres)
- Database configured in .env
- Valid database connection

Usage:
    pytest backend/tests/test_export_import_integration.py -v -m integration

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
from models.ai_service import AIService
from models.app import App
from services.ai_service_export_service import AIServiceExportService
from services.ai_service_import_service import AIServiceImportService
from schemas.export_schemas import AIServiceExportFileSchema
from schemas.import_schemas import ConflictMode, ComponentType


# ==================== FIXTURES ====================


@pytest.fixture(scope="function")
def test_app(db_session: Session):
    """Create a test app for testing."""
    # Check if app exists
    app = db_session.query(App).filter(App.name == "Test App Export").first()
    
    if not app:
        app = App(
            name="Test App Export",
            slug="test-app-export"
        )
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        created = True
    else:
        created = False
    
    yield app
    
    # Cleanup: Delete test AI services first to avoid foreign key issues
    if created:
        db_session.query(AIService).filter(AIService.app_id == app.app_id).delete()
        db_session.commit()
    
    # Cleanup only if we created it
    if created:
        db_session.delete(app)
        db_session.commit()


@pytest.fixture(scope="function")
def sample_ai_service(db_session: Session, test_app: App):
    """Create a sample AI service for testing."""
    service = AIService(
        app_id=test_app.app_id,
        name=f"Test GPT-4 Service {datetime.now().timestamp()}",
        provider="OpenAI",
        description="gpt-4",
        endpoint="https://api.openai.com/v1",
        api_key="sk-test-key-should-be-sanitized",
        api_version="v1"
    )
    db_session.add(service)
    db_session.commit()
    db_session.refresh(service)
    
    yield service
    
    # Cleanup
    try:
        db_session.delete(service)
        db_session.commit()
    except:
        db_session.rollback()


# ==================== INTEGRATION TESTS ====================


@pytest.mark.integration
class TestAIServiceExportIntegration:
    """Integration tests for AI Service export with real database."""
    
    def test_export_ai_service_success(
        self, db_session: Session, sample_ai_service: AIService
    ):
        """Test successful export of AI service from database."""
        export_service = AIServiceExportService(db_session)
        
        export_data = export_service.export_ai_service(
            sample_ai_service.service_id,
            sample_ai_service.app_id,
            user_id=1
        )
        
        # Verify export structure
        assert isinstance(export_data, AIServiceExportFileSchema)
        assert export_data.metadata.export_version == "1.0.0"
        assert export_data.metadata.source_app_id == sample_ai_service.app_id
        assert export_data.ai_service.name == sample_ai_service.name
        assert export_data.ai_service.provider == sample_ai_service.provider
        assert export_data.ai_service.model_name == sample_ai_service.description
        assert export_data.ai_service.endpoint == sample_ai_service.endpoint
    
    def test_export_sanitizes_api_key(
        self, db_session: Session, sample_ai_service: AIService
    ):
        """Test that API key is sanitized in export (CRITICAL SECURITY TEST)."""
        export_service = AIServiceExportService(db_session)
        
        # Verify service has API key in database
        assert sample_ai_service.api_key == "sk-test-key-should-be-sanitized"
        
        # Export
        export_data = export_service.export_ai_service(
            sample_ai_service.service_id,
            sample_ai_service.app_id,
            user_id=1
        )
        
        # CRITICAL: API key must be None in export
        assert export_data.ai_service.api_key is None
    
    def test_export_nonexistent_service(self, db_session: Session, test_app: App):
        """Test export of non-existent service raises error."""
        export_service = AIServiceExportService(db_session)
        
        with pytest.raises(ValueError, match="not found"):
            export_service.export_ai_service(
                service_id=99999,
                app_id=test_app.app_id,
                user_id=1
            )
    
    def test_export_wrong_app_id(
        self, db_session: Session, sample_ai_service: AIService
    ):
        """Test export with wrong app_id raises error."""
        export_service = AIServiceExportService(db_session)
        
        with pytest.raises(ValueError, match="not found"):
            export_service.export_ai_service(
                sample_ai_service.service_id,
                app_id=99999,  # Wrong app ID
                user_id=1
            )
    
    def test_export_to_json_file(
        self, db_session: Session, sample_ai_service: AIService, tmp_path
    ):
        """Test exporting to actual JSON file."""
        export_service = AIServiceExportService(db_session)
        
        export_data = export_service.export_ai_service(
            sample_ai_service.service_id,
            sample_ai_service.app_id,
            user_id=1
        )
        
        # Write to file
        export_file = tmp_path / "test_export.json"
        with open(export_file, 'w') as f:
            json.dump(export_data.model_dump(mode='json'), f, indent=2, default=str)
        
        # Verify file exists and is valid JSON
        assert export_file.exists()
        
        with open(export_file, 'r') as f:
            loaded_data = json.load(f)
        
        assert loaded_data['ai_service']['api_key'] is None
        assert loaded_data['ai_service']['name'] == sample_ai_service.name


@pytest.mark.integration
class TestAIServiceImportIntegration:
    """Integration tests for AI Service import with real database."""
    
    def test_import_new_service_success(
        self, db_session: Session, test_app: App, sample_ai_service: AIService
    ):
        """Test importing a new service successfully."""
        # Export first
        export_service = AIServiceExportService(db_session)
        export_data = export_service.export_ai_service(
            sample_ai_service.service_id,
            sample_ai_service.app_id,
            user_id=1
        )
        
        # Modify name to make it unique
        unique_name = f"Imported Service {datetime.now().timestamp()}"
        export_data.ai_service.name = unique_name
        
        # Import
        import_service = AIServiceImportService(db_session)
        summary = import_service.import_ai_service(
            export_data,
            app_id=test_app.app_id,
            user_id=1,
            conflict_mode=ConflictMode.FAIL
        )
        
        assert summary.component_type == ComponentType.AI_SERVICE
        assert summary.component_name == unique_name
        assert summary.created is True
        assert any("Configure API key" in step for step in summary.next_steps)
        
        # Verify in database
        created_service = db_session.query(AIService).filter(
            AIService.name == unique_name,
            AIService.app_id == test_app.app_id
        ).first()
        assert created_service is not None
        assert created_service.api_key is None  # Should be None after import
        assert created_service.provider == export_data.ai_service.provider
        
        # Cleanup
        db_session.delete(created_service)
        db_session.commit()
    
    def test_import_fail_mode_with_conflict(
        self, db_session: Session, sample_ai_service: AIService
    ):
        """Test FAIL mode raises error when service exists."""
        # Export existing service
        export_service = AIServiceExportService(db_session)
        export_data = export_service.export_ai_service(
            sample_ai_service.service_id,
            sample_ai_service.app_id,
            user_id=1
        )
        
        # Try to import with same name (should fail)
        import_service = AIServiceImportService(db_session)
        
        with pytest.raises(ValueError, match="already exists"):
            import_service.import_ai_service(
                export_data,
                app_id=sample_ai_service.app_id,
                user_id=1,
                conflict_mode=ConflictMode.FAIL
            )
    
    def test_import_rename_mode_auto_generates_name(
        self, db_session: Session, sample_ai_service: AIService
    ):
        """Test RENAME mode auto-generates unique name."""
        # Export existing service
        export_service = AIServiceExportService(db_session)
        export_data = export_service.export_ai_service(
            sample_ai_service.service_id,
            sample_ai_service.app_id,
            user_id=1
        )
        
        original_name = export_data.ai_service.name
        
        # Import with RENAME mode
        import_service = AIServiceImportService(db_session)
        summary = import_service.import_ai_service(
            export_data,
            app_id=sample_ai_service.app_id,
            user_id=1,
            conflict_mode=ConflictMode.RENAME
        )
        
        assert summary.created is True
        assert summary.component_name != original_name
        assert "imported" in summary.component_name.lower()
        
        # Verify in database
        created_service = db_session.query(AIService).get(summary.component_id)
        assert created_service is not None
        assert created_service.name != original_name
        
        # Cleanup
        db_session.delete(created_service)
        db_session.commit()
    
    def test_import_rename_mode_with_custom_name(
        self, db_session: Session, test_app: App, sample_ai_service: AIService
    ):
        """Test RENAME mode with custom name."""
        # Export
        export_service = AIServiceExportService(db_session)
        export_data = export_service.export_ai_service(
            sample_ai_service.service_id,
            sample_ai_service.app_id,
            user_id=1
        )
        
        custom_name = f"Custom Import {datetime.now().timestamp()}"
        
        # Import with custom name
        import_service = AIServiceImportService(db_session)
        summary = import_service.import_ai_service(
            export_data,
            app_id=test_app.app_id,
            user_id=1,
            conflict_mode=ConflictMode.RENAME,
            new_name=custom_name
        )
        
        assert summary.created is True
        assert summary.component_name == custom_name
        
        # Verify in database
        created_service = db_session.query(AIService).filter(
            AIService.name == custom_name
        ).first()
        assert created_service is not None
        
        # Cleanup
        db_session.delete(created_service)
        db_session.commit()
    
    def test_import_override_mode_updates_existing(
        self, db_session: Session, sample_ai_service: AIService
    ):
        """Test OVERRIDE mode updates existing service."""
        original_api_key = sample_ai_service.api_key
        original_description = sample_ai_service.description
        
        # Export
        export_service = AIServiceExportService(db_session)
        export_data = export_service.export_ai_service(
            sample_ai_service.service_id,
            sample_ai_service.app_id,
            user_id=1
        )
        
        # Modify export data
        export_data.ai_service.model_name = "gpt-4-turbo"
        export_data.ai_service.description = "Updated Description"
        
        # Import with OVERRIDE
        import_service = AIServiceImportService(db_session)
        summary = import_service.import_ai_service(
            export_data,
            app_id=sample_ai_service.app_id,
            user_id=1,
            conflict_mode=ConflictMode.OVERRIDE
        )
        
        assert summary.created is False
        assert summary.component_id == sample_ai_service.service_id
        assert any("API key preserved" in warning for warning in summary.warnings)
        
        # Verify update in database
        db_session.refresh(sample_ai_service)
        assert sample_ai_service.description == "gpt-4-turbo"
        assert sample_ai_service.api_key == original_api_key  # Preserved
    
    def test_import_preserves_api_key_on_override(
        self, db_session: Session, sample_ai_service: AIService
    ):
        """Test that OVERRIDE mode preserves existing API key (CRITICAL SECURITY TEST)."""
        original_api_key = sample_ai_service.api_key
        assert original_api_key is not None
        
        # Export and re-import with OVERRIDE
        export_service = AIServiceExportService(db_session)
        export_data = export_service.export_ai_service(
            sample_ai_service.service_id,
            sample_ai_service.app_id,
            user_id=1
        )
        
        # Verify export has None API key
        assert export_data.ai_service.api_key is None
        
        import_service = AIServiceImportService(db_session)
        summary = import_service.import_ai_service(
            export_data,
            app_id=sample_ai_service.app_id,
            user_id=1,
            conflict_mode=ConflictMode.OVERRIDE
        )
        
        # Verify API key was preserved
        db_session.refresh(sample_ai_service)
        assert sample_ai_service.api_key == original_api_key
    
    def test_import_from_json_file(
        self, db_session: Session, test_app: App, sample_ai_service: AIService, tmp_path
    ):
        """Test importing from actual JSON file."""
        # Export to file
        export_service = AIServiceExportService(db_session)
        export_data = export_service.export_ai_service(
            sample_ai_service.service_id,
            sample_ai_service.app_id,
            user_id=1
        )
        
        # Modify name to make it unique
        unique_name = f"File Import {datetime.now().timestamp()}"
        export_data.ai_service.name = unique_name
        
        export_file = tmp_path / "test_import.json"
        with open(export_file, 'w') as f:
            json.dump(export_data.model_dump(mode='json'), f, indent=2, default=str)
        
        # Read from file and import
        with open(export_file, 'r') as f:
            file_data = json.load(f)
        
        import_data = AIServiceExportFileSchema(**file_data)
        
        import_service = AIServiceImportService(db_session)
        summary = import_service.import_ai_service(
            import_data,
            app_id=test_app.app_id,
            user_id=1,
            conflict_mode=ConflictMode.FAIL
        )
        
        assert summary.created is True
        assert summary.component_name == unique_name
        
        # Verify in database
        created_service = db_session.query(AIService).filter(
            AIService.name == unique_name
        ).first()
        assert created_service is not None
        
        # Cleanup
        db_session.delete(created_service)
        db_session.commit()


@pytest.mark.integration
class TestExportImportRoundTrip:
    """Integration tests for complete export/import round trip."""
    
    def test_export_import_roundtrip(
        self, db_session: Session, test_app: App, sample_ai_service: AIService
    ):
        """Test complete export and import cycle."""
        # Step 1: Export
        export_service = AIServiceExportService(db_session)
        export_data = export_service.export_ai_service(
            sample_ai_service.service_id,
            sample_ai_service.app_id,
            user_id=1
        )
        
        # Step 2: Modify name for import
        original_name = export_data.ai_service.name
        export_data.ai_service.name = f"RoundTrip {datetime.now().timestamp()}"
        
        # Step 3: Import
        import_service = AIServiceImportService(db_session)
        summary = import_service.import_ai_service(
            export_data,
            app_id=test_app.app_id,
            user_id=1,
            conflict_mode=ConflictMode.FAIL
        )
        
        # Step 4: Verify imported service matches original (except name and API key)
        imported_service = db_session.query(AIService).get(summary.component_id)
        
        assert imported_service.provider == sample_ai_service.provider
        assert imported_service.description == sample_ai_service.description
        assert imported_service.endpoint == sample_ai_service.endpoint
        assert imported_service.api_version == sample_ai_service.api_version
        assert imported_service.api_key is None  # API key not imported
        
        # Cleanup
        db_session.delete(imported_service)
        db_session.commit()
    
    def test_multiple_imports_rename_mode(
        self, db_session: Session, sample_ai_service: AIService
    ):
        """Test multiple imports with RENAME mode create unique names."""
        export_service = AIServiceExportService(db_session)
        import_service = AIServiceImportService(db_session)
        
        # Export once
        export_data = export_service.export_ai_service(
            sample_ai_service.service_id,
            sample_ai_service.app_id,
            user_id=1
        )
        
        imported_services = []
        
        # Import 3 times with RENAME mode
        for i in range(3):
            summary = import_service.import_ai_service(
                export_data,
                app_id=sample_ai_service.app_id,
                user_id=1,
                conflict_mode=ConflictMode.RENAME
            )
            
            imported_service = db_session.query(AIService).get(summary.component_id)
            imported_services.append(imported_service)
        
        # Verify all have unique names
        names = [s.name for s in imported_services]
        assert len(names) == len(set(names))  # All names are unique
        
        # All names should contain "imported"
        for name in names:
            assert "imported" in name.lower()
        
        # Cleanup
        for service in imported_services:
            db_session.delete(service)
        db_session.commit()
