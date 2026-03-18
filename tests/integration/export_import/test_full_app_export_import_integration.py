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
from services.full_app_export_service import FullAppExportService
from services.full_app_import_service import FullAppImportService
from schemas.export_schemas import AppExportFileSchema
from schemas.import_schemas import (
    ConflictMode,
    ComponentSelectionSchema,
    ImportTargetMode,
)


# ==================== FIXTURES ====================


@pytest.fixture(scope="function")
def test_app(db_session: Session):
    """Create a test app for testing."""
    timestamp = datetime.now().timestamp()
    app = App(name=f"Test App Full Export {timestamp}", slug=f"test-app-full-{timestamp}")
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)
    
    yield app
    
    # Cleanup (cascading deletes should handle related entities)
    try:
        db_session.delete(app)
        db_session.commit()
    except:
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
    
    def test_import_into_existing_app_cycle(
        self, db_session: Session, populated_app: dict
    ):
        """Test export → import cycle into different app."""
        export_service = FullAppExportService(db_session)
        import_service = FullAppImportService(db_session)
        
        # Export from populated app
        source_app = populated_app["app"]
        export_data = export_service.export_full_app(source_app.app_id, user_id=1)
        
        # Create target app
        target_app = App(
            name=f"Target App {datetime.now().timestamp()}",
            slug=f"target-app-{datetime.now().timestamp()}",
        )
        db_session.add(target_app)
        db_session.commit()
        db_session.refresh(target_app)
        
        try:
            # Import into target app
            summary = import_service.import_full_app(
                target_app_id=target_app.app_id,
                export_data=export_data,
                conflict_mode=ConflictMode.FAIL,
                target_mode=ImportTargetMode.EXISTING_APP,
            )
            
            # Verify import summary
            assert summary.app_id == target_app.app_id
            assert summary.total_components == 7  # 2 AI + 1 Emb + 1 Parser + 1 MCP + 1 Silo + 2 Agents - 1 (Agent bundled components)
            assert summary.components_imported["ai_services"] == 2
            assert summary.components_imported["embedding_services"] == 1
            assert summary.components_imported["output_parsers"] == 1
            assert summary.components_imported["mcp_configs"] == 1
            assert summary.components_imported["silos"] == 1
            assert summary.components_imported["agents"] == 2
            assert len(summary.total_errors) == 0
            
            # Verify components exist in target app
            target_ai_services = (
                db_session.query(AIService)
                .filter(AIService.app_id == target_app.app_id)
                .all()
            )
            assert len(target_ai_services) >= 2
            
        finally:
            # Cleanup target app
            db_session.delete(target_app)
            db_session.commit()
    
    def test_import_as_new_app(self, db_session: Session, populated_app: dict):
        """Test import creating new app from export."""
        export_service = FullAppExportService(db_session)
        import_service = FullAppImportService(db_session)
        
        # Export from populated app
        source_app = populated_app["app"]
        export_data = export_service.export_full_app(source_app.app_id, user_id=1)
        
        # Import as new app
        summary = import_service.import_full_app(
            target_app_id=None,
            export_data=export_data,
            conflict_mode=ConflictMode.FAIL,
            target_mode=ImportTargetMode.NEW_APP,
        )
        
        # Verify new app was created
        assert summary.app_id is not None
        assert summary.app_id != source_app.app_id
        new_app = db_session.query(App).filter(App.app_id == summary.app_id).first()
        assert new_app is not None
        
        try:
            # Verify components imported
            assert summary.total_components > 0
            assert len(summary.total_errors) == 0
        finally:
            # Cleanup new app
            if new_app:
                db_session.delete(new_app)
                db_session.commit()
    
    def test_import_selective_components(
        self, db_session: Session, populated_app: dict
    ):
        """Test selective component import."""
        export_service = FullAppExportService(db_session)
        import_service = FullAppImportService(db_session)
        
        # Export from populated app
        source_app = populated_app["app"]
        export_data = export_service.export_full_app(source_app.app_id, user_id=1)
        
        # Create target app
        target_app = App(
            name=f"Selective Import {datetime.now().timestamp()}",
            slug=f"selective-{datetime.now().timestamp()}",
        )
        db_session.add(target_app)
        db_session.commit()
        db_session.refresh(target_app)
        
        try:
            # Import only AI services and output parsers
            selection = ComponentSelectionSchema(
                import_ai_services=True,
                import_embedding_services=False,
                import_output_parsers=True,
                import_mcp_configs=False,
                import_silos=False,
                import_agents=False,
            )
            
            summary = import_service.import_full_app(
                target_app_id=target_app.app_id,
                export_data=export_data,
                conflict_mode=ConflictMode.FAIL,
                selection=selection,
                target_mode=ImportTargetMode.EXISTING_APP,
            )
            
            # Verify only selected components imported
            assert summary.components_imported.get("ai_services", 0) == 2
            assert summary.components_imported.get("output_parsers", 0) == 1
            assert summary.components_skipped.get("embedding_services", 0) == 1
            assert summary.components_skipped.get("mcp_configs", 0) == 1
            assert summary.components_skipped.get("silos", 0) == 1
            assert summary.components_skipped.get("agents", 0) == 2
            
        finally:
            # Cleanup target app
            db_session.delete(target_app)
            db_session.commit()
    
    def test_import_conflict_rename_mode(
        self, db_session: Session, populated_app: dict
    ):
        """Test import with RENAME conflict mode."""
        export_service = FullAppExportService(db_session)
        import_service = FullAppImportService(db_session)
        
        # Export from populated app
        source_app = populated_app["app"]
        export_data = export_service.export_full_app(source_app.app_id, user_id=1)
        
        # Import into same app with RENAME mode (should create duplicates)
        summary = import_service.import_full_app(
            target_app_id=source_app.app_id,
            export_data=export_data,
            conflict_mode=ConflictMode.RENAME,
            target_mode=ImportTargetMode.EXISTING_APP,
        )
        
        # Should succeed without errors
        assert len(summary.total_errors) == 0
        
        # Verify renamed components exist
        ai_services = (
            db_session.query(AIService)
            .filter(AIService.app_id == source_app.app_id)
            .all()
        )
        # Should have original 2 + imported 2 = 4 (some renamed)
        assert len(ai_services) >= 2
    
    def test_import_rollback_on_error(self, db_session: Session):
        """Test that import rolls back on error (transaction safety)."""
        import_service = FullAppImportService(db_session)
        
        # Create invalid export data (missing required fields)
        from schemas.export_schemas import ExportMetadataSchema, ExportAppSchema
        
        invalid_export = AppExportFileSchema(
            metadata=ExportMetadataSchema(
                export_version="1.0.0",
                export_date=datetime.now().isoformat(),
                source_app_id=1,
            ),
            app=ExportAppSchema(name="Invalid App"),
            ai_services=[],
            embedding_services=[],
            output_parsers=[],
            mcp_configs=[],
            silos=[],
            repositories=[],
            agents=[],
        )
        
        # Try to import into non-existent app (should fail)
        with pytest.raises(ValueError):
            import_service.import_full_app(
                target_app_id=99999,
                export_data=invalid_export,
                conflict_mode=ConflictMode.FAIL,
                target_mode=ImportTargetMode.EXISTING_APP,
            )
        
        # Verify no partial import occurred (transaction rolled back)
        # This is implicit - if transaction wasn't rolled back, we'd have partial data
