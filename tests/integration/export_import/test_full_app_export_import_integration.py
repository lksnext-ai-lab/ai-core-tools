"""
Integration tests for Full App Export/Import with real PostgreSQL database.

These tests require:
- PostgreSQL running (docker compose up -d postgres)
- Database configured in .env
- Valid database connection

Usage:
    pytest backend/tests/test_full_app_export_import_integration.py -v -m integration

Mark as integration tests:
    @pytest.mark.integration
"""

import pytest
import json
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session

from models.app import App
from models.ai_service import AIService
from models.embedding_service import EmbeddingService
from models.output_parser import OutputParser
from models.mcp_config import MCPConfig
from models.silo import Silo
from models.agent import Agent
from models.user import User
from services.full_app_export_service import FullAppExportService
from services.full_app_import_service import FullAppImportService
from schemas.export_schemas import AppExportFileSchema
from schemas.import_schemas import ConflictMode


# ==================== FIXTURES ====================


@pytest.fixture(scope="function")
def test_app(db_session: Session):
    """Create a test app with an owner user for testing."""
    timestamp = datetime.now().timestamp()
    owner = User(email=f"owner-{timestamp}@test.com", name="Test Owner")
    db_session.add(owner)
    db_session.flush()

    app = App(
        name=f"Test App Full Export {timestamp}",
        slug=f"test-app-full-{timestamp}",
        owner_id=owner.user_id,
    )
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)

    yield app

    # Cleanup (cascading deletes should handle related entities)
    try:
        db_session.delete(app)
        db_session.flush()
        db_session.delete(owner)
        db_session.commit()
    except Exception:
        db_session.rollback()


@pytest.fixture(scope="function")
def populated_app(db_session: Session, test_app: App):
    """Create an app with sample data for all component types."""
    # Create 2 AI services
    ai_service1 = AIService(
        app_id=test_app.app_id,
        name="GPT-4 Service",
        provider="OpenAI",
        description="gpt-4",
        endpoint="https://api.openai.com/v1",
        api_key="sk-test-key-1",
        api_version="v1",
    )
    ai_service2 = AIService(
        app_id=test_app.app_id,
        name="Claude Service",
        provider="Anthropic",
        description="claude-3-opus-20240229",
        endpoint="https://api.anthropic.com/v1",
        api_key="sk-ant-test-key-2",
        api_version="2023-06-01",
    )
    db_session.add_all([ai_service1, ai_service2])
    db_session.flush()
    
    # Create 1 embedding service
    embedding_service = EmbeddingService(
        app_id=test_app.app_id,
        name="OpenAI Embeddings",
        provider="OpenAI",
        description="text-embedding-3-small",
        api_key="sk-embedding-test-key",
        endpoint="https://api.openai.com/v1",
    )
    db_session.add(embedding_service)
    db_session.flush()
    
    # Create 1 output parser
    output_parser = OutputParser(
        app_id=test_app.app_id,
        name="Contact Parser",
        description="Parse contact information",
        fields=[
            {
                "field_name": "name",
                "field_type": "str",
                "field_description": "Contact name",
            },
            {
                "field_name": "email",
                "field_type": "str",
                "field_description": "Email address",
            },
        ],
    )
    db_session.add(output_parser)
    db_session.flush()
    
    # Create 1 MCP config
    mcp_config = MCPConfig(
        app_id=test_app.app_id,
        name="Test MCP",
        description="Test MCP server",
        config={
            "test-server": {
                "command": "uvx",
                "args": ["test-server"],
                "env": {"API_KEY": "secret-value"},  # Should be sanitized
            }
        },
    )
    db_session.add(mcp_config)
    db_session.flush()
    
    # Create 1 silo
    silo = Silo(
        app_id=test_app.app_id,
        name="Knowledge Base",
        description="Test knowledge base",
        silo_type="CUSTOM",
        embedding_service_id=embedding_service.service_id,
        metadata_definition_id=output_parser.parser_id,
    )
    db_session.add(silo)
    db_session.flush()
    
    # Create 2 agents
    agent1 = Agent(
        app_id=test_app.app_id,
        name="Assistant Agent",
        description="General assistant",
        system_prompt="You are a helpful assistant",
        service_id=ai_service1.service_id,
        silo_id=silo.silo_id,
        has_memory=True,
        memory_max_messages=10,
        temperature=0.7,
    )
    agent2 = Agent(
        app_id=test_app.app_id,
        name="Analyzer Agent",
        description="Data analyzer",
        system_prompt="You analyze data",
        service_id=ai_service2.service_id,
        output_parser_id=output_parser.parser_id,
        has_memory=False,
        temperature=0.3,
    )
    db_session.add_all([agent1, agent2])
    
    db_session.commit()
    
    return {
        "app": test_app,
        "ai_services": [ai_service1, ai_service2],
        "embedding_services": [embedding_service],
        "output_parsers": [output_parser],
        "mcp_configs": [mcp_config],
        "silos": [silo],
        "agents": [agent1, agent2],
    }


# ==================== INTEGRATION TESTS ====================


@pytest.mark.integration
class TestFullAppExportIntegration:
    """Integration tests for full app export with real database."""
    
    def test_export_full_app_structure(self, db_session: Session, populated_app: dict):
        """Test full app export includes all component types."""
        export_service = FullAppExportService(db_session)
        app = populated_app["app"]
        
        export_data = export_service.export_full_app(app.app_id, user_id=1)
        
        # Verify export structure
        assert isinstance(export_data, AppExportFileSchema)
        assert export_data.metadata.export_version == "1.0.0"
        assert export_data.metadata.source_app_id == app.app_id
        assert export_data.app.name == app.name
        
        # Verify component counts
        assert len(export_data.ai_services) == 2
        assert len(export_data.embedding_services) == 1
        assert len(export_data.output_parsers) == 1
        assert len(export_data.mcp_configs) == 1
        assert len(export_data.silos) == 1
        assert len(export_data.repositories) == 0  # Phase 6 not implemented
        assert len(export_data.agents) == 2
    
    def test_export_excludes_secrets(self, db_session: Session, populated_app: dict):
        """Test that all secrets are sanitized in export (CRITICAL SECURITY TEST)."""
        export_service = FullAppExportService(db_session)
        app = populated_app["app"]
        
        export_data = export_service.export_full_app(app.app_id, user_id=1)
        
        # Convert to JSON and search for secret patterns
        export_json = export_data.model_dump_json()
        
        # CRITICAL: No API keys or secrets should be in export
        assert "sk-test-key" not in export_json
        assert "sk-ant-test" not in export_json
        assert "sk-embedding" not in export_json
        assert "secret-value" not in export_json
        
        # Verify AI service API keys are None
        for ai_service in export_data.ai_services:
            assert ai_service.api_key is None
        
        # Verify embedding service API keys are None
        for embedding_service in export_data.embedding_services:
            assert embedding_service.api_key is None
        
        # Verify MCP config secrets are sanitized
        for mcp_config in export_data.mcp_configs:
            if mcp_config.config:
                assert "secret-value" not in str(mcp_config.config)
    
    def test_export_empty_app(self, db_session: Session, test_app: App):
        """Test export of app with no components."""
        export_service = FullAppExportService(db_session)
        
        export_data = export_service.export_full_app(test_app.app_id, user_id=1)
        
        # Should have valid structure with empty arrays
        assert len(export_data.ai_services) == 0
        assert len(export_data.embedding_services) == 0
        assert len(export_data.output_parsers) == 0
        assert len(export_data.mcp_configs) == 0
        assert len(export_data.silos) == 0
        assert len(export_data.agents) == 0
    
    def test_export_nonexistent_app(self, db_session: Session):
        """Test export of non-existent app raises error."""
        export_service = FullAppExportService(db_session)
        
        with pytest.raises(ValueError, match="not found"):
            export_service.export_full_app(99999, user_id=1)


@pytest.mark.integration
class TestFullAppImportIntegration:
    """Integration tests for full app import with real database."""

    def test_import_creates_new_app_cycle(
        self, db_session: Session, populated_app: dict
    ):
        """Test export → import cycle always creates a new app."""
        export_service = FullAppExportService(db_session)
        import_service = FullAppImportService(db_session)

        source_app = populated_app["app"]
        export_data = export_service.export_full_app(source_app.app_id, user_id=source_app.owner_id)

        new_name = f"Imported App {datetime.now().timestamp()}"
        summary = import_service.import_full_app(
            export_data=export_data,
            user_id=source_app.owner_id,
            conflict_mode=ConflictMode.FAIL,
            new_name=new_name,
        )

        imported_app = None
        try:
            assert summary.app_id != source_app.app_id
            imported_app = db_session.query(App).filter(
                App.app_id == summary.app_id
            ).first()
            assert imported_app is not None
            assert imported_app.name == new_name

            assert summary.total_components >= 7
            assert summary.components_imported.get("ai_services", 0) == 2
            assert summary.components_imported.get("embedding_services", 0) == 1
            assert summary.components_imported.get("output_parsers", 0) == 1
            assert summary.components_imported.get("mcp_configs", 0) == 1
            assert summary.components_imported.get("agents", 0) == 2
            assert len(summary.total_errors) == 0

            new_ai_services = (
                db_session.query(AIService)
                .filter(AIService.app_id == summary.app_id)
                .all()
            )
            assert len(new_ai_services) == 2
        finally:
            if imported_app:
                db_session.delete(imported_app)
                db_session.commit()

    def test_import_as_new_app(self, db_session: Session, populated_app: dict):
        """Test import creating new app with custom name."""
        export_service = FullAppExportService(db_session)
        import_service = FullAppImportService(db_session)

        source_app = populated_app["app"]
        export_data = export_service.export_full_app(source_app.app_id, user_id=source_app.owner_id)

        custom_name = f"Custom Import {datetime.now().timestamp()}"
        summary = import_service.import_full_app(
            export_data=export_data,
            user_id=source_app.owner_id,
            conflict_mode=ConflictMode.FAIL,
            new_name=custom_name,
        )

        imported_app = None
        try:
            assert summary.app_id is not None
            assert summary.app_id != source_app.app_id
            imported_app = db_session.query(App).filter(
                App.app_id == summary.app_id
            ).first()
            assert imported_app is not None
            assert imported_app.name == custom_name
            assert summary.total_components > 0
            assert len(summary.total_errors) == 0
        finally:
            if imported_app:
                db_session.delete(imported_app)
                db_session.commit()

    def test_import_selective_components(
        self, db_session: Session, populated_app: dict
    ):
        """Test selective component import using component_selection dict."""
        export_service = FullAppExportService(db_session)
        import_service = FullAppImportService(db_session)

        source_app = populated_app["app"]
        export_data = export_service.export_full_app(source_app.app_id, user_id=source_app.owner_id)

        # Include only AI services and output parsers by providing their names.
        # Keys absent from component_selection → exclude all of that type.
        component_selection = {
            "ai_service": [s.name for s in export_data.ai_services],
            "output_parser": [p.name for p in export_data.output_parsers],
        }

        new_name = f"Selective Import {datetime.now().timestamp()}"
        summary = import_service.import_full_app(
            export_data=export_data,
            user_id=source_app.owner_id,
            conflict_mode=ConflictMode.FAIL,
            new_name=new_name,
            component_selection=component_selection,
        )

        imported_app = None
        try:
            imported_app = db_session.query(App).filter(
                App.app_id == summary.app_id
            ).first()

            assert summary.components_imported.get("ai_services", 0) == 2
            assert summary.components_imported.get("output_parsers", 0) == 1
            assert summary.components_imported.get("embedding_services", 0) == 0
            assert summary.components_imported.get("mcp_configs", 0) == 0
            assert summary.components_imported.get("silos", 0) == 0
            assert summary.components_imported.get("agents", 0) == 0
        finally:
            if imported_app:
                db_session.delete(imported_app)
                db_session.commit()

    def test_import_conflict_rename_mode(
        self, db_session: Session, populated_app: dict
    ):
        """Test import with RENAME conflict mode handles name collisions."""
        export_service = FullAppExportService(db_session)
        import_service = FullAppImportService(db_session)

        source_app = populated_app["app"]
        owner_id = source_app.owner_id
        export_data = export_service.export_full_app(source_app.app_id, user_id=owner_id)

        fixed_name = f"Import Rename Test {datetime.now().timestamp()}"

        # First import — creates a new app with fixed_name
        first_summary = import_service.import_full_app(
            export_data=export_data,
            user_id=owner_id,
            conflict_mode=ConflictMode.RENAME,
            new_name=fixed_name,
        )
        assert len(first_summary.total_errors) == 0

        # Second import with same name — RENAME mode auto-renames
        second_summary = import_service.import_full_app(
            export_data=export_data,
            user_id=owner_id,
            conflict_mode=ConflictMode.RENAME,
            new_name=fixed_name,
        )
        assert len(second_summary.total_errors) == 0
        assert second_summary.app_id != first_summary.app_id

        for app_id in [first_summary.app_id, second_summary.app_id]:
            app = db_session.query(App).filter(App.app_id == app_id).first()
            if app:
                db_session.delete(app)
        db_session.commit()

    def test_import_rollback_on_error(
        self, db_session: Session, populated_app: dict
    ):
        """Test that import raises ValueError on name conflict with FAIL mode."""
        export_service = FullAppExportService(db_session)
        import_service = FullAppImportService(db_session)

        source_app = populated_app["app"]
        owner_id = source_app.owner_id
        export_data = export_service.export_full_app(source_app.app_id, user_id=owner_id)

        # First import — creates a new app with a controlled name
        fixed_name = f"Rollback Test {datetime.now().timestamp()}"
        first_summary = import_service.import_full_app(
            export_data=export_data,
            user_id=owner_id,
            conflict_mode=ConflictMode.RENAME,
            new_name=fixed_name,
        )
        created_app = db_session.query(App).filter(
            App.app_id == first_summary.app_id
        ).first()

        try:
            # Second import with same name + FAIL mode → ValueError
            with pytest.raises(ValueError, match="already exists"):
                import_service.import_full_app(
                    export_data=export_data,
                    user_id=owner_id,
                    conflict_mode=ConflictMode.FAIL,
                    new_name=fixed_name,
                )

            # Only one app with that name should exist
            all_with_name = (
                db_session.query(App).filter(App.name == fixed_name).all()
            )
            assert len(all_with_name) == 1
        finally:
            if created_app:
                db_session.delete(created_app)
                db_session.commit()
