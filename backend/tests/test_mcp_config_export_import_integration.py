"""
Integration tests for MCP Config Export/Import with real PostgreSQL database.

These tests require:
- PostgreSQL running (docker compose up -d postgres)
- Database configured in .env
- Valid database connection

Usage:
    pytest backend/tests/test_mcp_config_export_import_integration.py -v -m integration

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
from models.mcp_config import MCPConfig
from models.app import App
from services.mcp_config_export_service import MCPConfigExportService
from services.mcp_config_import_service import MCPConfigImportService
from schemas.export_schemas import (
    MCPConfigExportFileSchema,
    ExportMCPConfigSchema,
    ExportMetadataSchema
)
from schemas.import_schemas import ConflictMode, ComponentType


# ==================== FIXTURES ====================


@pytest.fixture(scope="function")
def test_app(db_session: Session):
    """Create a test app for testing."""
    # Check if app exists
    app = (
        db_session.query(App)
        .filter(App.name == "Test App MCP Export")
        .first()
    )

    if not app:
        app = App(name="Test App MCP Export", slug="test-app-mcp-export")
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        created = True
    else:
        created = False

    yield app

    # Cleanup: Delete test configs first
    if created:
        db_session.query(MCPConfig).filter(
            MCPConfig.app_id == app.app_id
        ).delete()
        db_session.commit()

    # Cleanup only if we created it
    if created:
        db_session.delete(app)
        db_session.commit()


@pytest.fixture(scope="function")
def sample_mcp_config(db_session: Session, test_app: App):
    """Create a sample MCP config with sensitive data for testing."""
    config_data = {
        "url": "http://localhost:8080/mcp",
        "api_key": "secret-key-12345",  # Should be sanitized
        "token": "bearer-token-xyz",  # Should be sanitized
        "timeout": 30,
        "headers": {
            "User-Agent": "TestClient/1.0",
            "Authorization": "Bearer secret"  # Should be sanitized
        },
        "features": {
            "streaming": True,
            "batch_size": 100
        }
    }

    mcp_config = MCPConfig(
        app_id=test_app.app_id,
        name=f"Test MCP Config {datetime.now().timestamp()}",
        description="Test MCP config for export/import",
        config=config_data,
        create_date=datetime.now()
    )
    db_session.add(mcp_config)
    db_session.commit()
    db_session.refresh(mcp_config)

    yield mcp_config

    # Cleanup
    try:
        db_session.delete(mcp_config)
        db_session.commit()
    except Exception:
        db_session.rollback()


@pytest.fixture
def sanitized_export_data():
    """Sample export data without secrets (for import testing)."""
    return MCPConfigExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
            exported_by="1",
            source_app_id=1
        ),
        mcp_config=ExportMCPConfigSchema(
            name="Imported Test MCP Config",
            description="Test config imported from file",
            config=json.dumps({
                "url": "http://localhost:8080/mcp",
                "timeout": 30,
                "headers": {"User-Agent": "TestClient/1.0"},
                "features": {"streaming": True, "batch_size": 100}
            })
        )
    )


# ==================== INTEGRATION TESTS ====================


@pytest.mark.integration
class TestMCPConfigExportIntegration:
    """Integration tests for MCP Config export with real database."""

    def test_export_mcp_config_success(
        self, db_session: Session, sample_mcp_config: MCPConfig
    ):
        """Test successful export of MCP config from database."""
        export_service = MCPConfigExportService(db_session)

        export_data = export_service.export_mcp_config(
            sample_mcp_config.config_id,
            sample_mcp_config.app_id,
            user_id=1,
        )

        # Verify export structure
        assert isinstance(export_data, MCPConfigExportFileSchema)

        # Verify metadata
        assert export_data.metadata.export_version == "1.0.0"
        assert export_data.metadata.exported_by == "1"
        assert export_data.metadata.source_app_id == sample_mcp_config.app_id
        assert export_data.metadata.export_date is not None

        # Verify config data
        assert export_data.mcp_config.name == sample_mcp_config.name
        assert (
            export_data.mcp_config.description ==
            sample_mcp_config.description
        )

    def test_export_sanitizes_sensitive_keys(
        self, db_session: Session, sample_mcp_config: MCPConfig
    ):
        """Test that sensitive keys are removed from exported config."""
        export_service = MCPConfigExportService(db_session)

        export_data = export_service.export_mcp_config(
            sample_mcp_config.config_id,
            sample_mcp_config.app_id,
            user_id=1,
        )

        # Parse exported config
        if export_data.mcp_config.config:
            config = json.loads(export_data.mcp_config.config)

            # Verify sensitive keys are removed
            assert "api_key" not in config
            assert "apiKey" not in config
            assert "token" not in config
            
            # Verify Authorization header was sanitized
            headers = config.get("headers", {})
            assert not any(k.lower() == "authorization" for k in headers.keys())

            # Verify non-sensitive keys are preserved
            assert config.get("url") == "http://localhost:8080/mcp"
            assert config.get("timeout") == 30
            assert "User-Agent" in config.get("headers", {})
            assert config.get("features", {}).get("streaming") is True

    def test_export_nonexistent_config(
        self, db_session: Session, test_app: App
    ):
        """Test export of non-existent config raises error."""
        export_service = MCPConfigExportService(db_session)

        with pytest.raises(ValueError, match="not found"):
            export_service.export_mcp_config(99999, test_app.app_id, user_id=1)

    def test_export_metadata_complete(
        self, db_session: Session, sample_mcp_config: MCPConfig
    ):
        """Test that export metadata is complete and valid."""
        export_service = MCPConfigExportService(db_session)

        export_data = export_service.export_mcp_config(
            sample_mcp_config.config_id,
            sample_mcp_config.app_id,
            user_id=1,
        )

        # Verify all metadata fields
        assert export_data.metadata.export_version is not None
        assert export_data.metadata.export_date is not None
        assert export_data.metadata.exported_by is not None
        assert export_data.metadata.source_app_id == sample_mcp_config.app_id


@pytest.mark.integration
class TestMCPConfigImportIntegration:
    """Integration tests for MCP Config import with real database."""

    def test_import_new_config_success(
        self, db_session: Session, test_app: App, sanitized_export_data
    ):
        """Test successful import of new MCP config."""
        import_service = MCPConfigImportService(db_session)

        summary = import_service.import_mcp_config(
            sanitized_export_data,
            test_app.app_id,
            conflict_mode=ConflictMode.FAIL
        )

        # Verify import summary
        assert summary.component_type == ComponentType.MCP_CONFIG
        assert summary.created is True
        assert summary.component_name == sanitized_export_data.mcp_config.name
        assert "Authentication tokens must be reconfigured" in summary.warnings

        # Verify config was created in database
        created_config = db_session.query(MCPConfig).get(summary.component_id)
        assert created_config is not None
        assert created_config.name == sanitized_export_data.mcp_config.name
        assert created_config.app_id == test_app.app_id

        # Cleanup
        db_session.delete(created_config)
        db_session.commit()

    def test_import_conflict_fail_mode(
        self, db_session: Session, sample_mcp_config: MCPConfig
    ):
        """Test import with FAIL mode raises error on name conflict."""
        # Create export data with same name as existing config
        conflict_data = MCPConfigExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=sample_mcp_config.app_id
            ),
            mcp_config=ExportMCPConfigSchema(
                name=sample_mcp_config.name,  # Same name
                description="Conflict test",
                config=json.dumps({"url": "http://test.com"})
            )
        )

        import_service = MCPConfigImportService(db_session)

        with pytest.raises(ValueError, match="already exists"):
            import_service.import_mcp_config(
                conflict_data,
                sample_mcp_config.app_id,
                conflict_mode=ConflictMode.FAIL
            )

    def test_import_conflict_rename_mode(
        self, db_session: Session, sample_mcp_config: MCPConfig
    ):
        """Test import with RENAME mode creates new config with modified name."""
        # Create export data with same name
        conflict_data = MCPConfigExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=sample_mcp_config.app_id
            ),
            mcp_config=ExportMCPConfigSchema(
                name=sample_mcp_config.name,
                description="Rename test",
                config=json.dumps({"url": "http://test.com"})
            )
        )

        import_service = MCPConfigImportService(db_session)

        summary = import_service.import_mcp_config(
            conflict_data,
            sample_mcp_config.app_id,
            conflict_mode=ConflictMode.RENAME
        )

        # Verify new config with different name
        assert summary.created is True
        assert summary.component_name != sample_mcp_config.name
        assert "imported" in summary.component_name.lower()

        # Cleanup
        created_config = db_session.query(MCPConfig).get(summary.component_id)
        if created_config:
            db_session.delete(created_config)
            db_session.commit()

    def test_import_conflict_rename_custom_name(
        self, db_session: Session, sample_mcp_config: MCPConfig
    ):
        """Test import with RENAME mode and custom name."""
        custom_name = f"Custom Name {datetime.now().timestamp()}"

        conflict_data = MCPConfigExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=sample_mcp_config.app_id
            ),
            mcp_config=ExportMCPConfigSchema(
                name=sample_mcp_config.name,
                description="Custom rename test",
                config=json.dumps({"url": "http://test.com"})
            )
        )

        import_service = MCPConfigImportService(db_session)

        summary = import_service.import_mcp_config(
            conflict_data,
            sample_mcp_config.app_id,
            conflict_mode=ConflictMode.RENAME,
            new_name=custom_name
        )

        # Verify custom name was used
        assert summary.component_name == custom_name

        # Cleanup
        created_config = db_session.query(MCPConfig).get(summary.component_id)
        if created_config:
            db_session.delete(created_config)
            db_session.commit()

    def test_import_conflict_override_mode(
        self, db_session: Session, sample_mcp_config: MCPConfig
    ):
        """Test import with OVERRIDE mode updates existing config."""
        # Remember original config with sensitive data
        original_config = json.loads(
            sample_mcp_config.config
            if isinstance(sample_mcp_config.config, str)
            else json.dumps(sample_mcp_config.config)
        )
        original_api_key = original_config.get("api_key")

        # Create export data with same name but different config
        override_data = MCPConfigExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now(),
                exported_by="1",
                source_app_id=sample_mcp_config.app_id
            ),
            mcp_config=ExportMCPConfigSchema(
                name=sample_mcp_config.name,
                description="Updated description",
                config=json.dumps({
                    "url": "http://updated.com",  # New URL
                    "timeout": 60  # New timeout
                })
            )
        )

        import_service = MCPConfigImportService(db_session)

        summary = import_service.import_mcp_config(
            override_data,
            sample_mcp_config.app_id,
            conflict_mode=ConflictMode.OVERRIDE
        )

        # Verify update (not creation)
        assert summary.created is False
        assert summary.component_id == sample_mcp_config.config_id
        assert "preserved" in " ".join(summary.warnings).lower()

        # Verify config was updated
        db_session.refresh(sample_mcp_config)
        updated_config = (
            json.loads(sample_mcp_config.config)
            if isinstance(sample_mcp_config.config, str)
            else sample_mcp_config.config
        )

        # Verify sensitive keys preserved
        assert updated_config.get("api_key") == original_api_key

        # Verify new values applied
        assert updated_config.get("url") == "http://updated.com"
        assert updated_config.get("timeout") == 60
