"""Integration tests for Silo export/import functionality."""

import pytest
from sqlalchemy.orm import Session
from datetime import datetime

from models.app import App
from models.user import User
from models.silo import Silo
from models.embedding_service import EmbeddingService
from models.output_parser import OutputParser
from schemas.export_schemas import (
    ExportSiloSchema,
    SiloExportFileSchema,
    ExportMetadataSchema,
    ExportEmbeddingServiceSchema,
    ExportOutputParserSchema,
)
from schemas.import_schemas import ConflictMode
from services.silo_export_service import SiloExportService
from services.silo_import_service import SiloImportService
from repositories.silo_repository import SiloRepository


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create test user."""
    user = User(
        email="test_silo@example.com",
        name="Test Silo User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_app(db_session: Session, test_user: User) -> App:
    """Create test app."""
    app = App(
        name="Test Silo App",
        owner_id=test_user.user_id,
    )
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)
    return app


@pytest.fixture
def test_app_id(test_app: App):
    """Fixture for test app ID."""
    return test_app.app_id


@pytest.fixture
def test_user_id(test_user: User):
    """Fixture for test user ID."""
    return test_user.user_id


@pytest.fixture
def embedding_service(db_session: Session, test_app_id: int) -> EmbeddingService:
    """Create test embedding service."""
    service = EmbeddingService(
        app_id=test_app_id,
        name="Test Embedding Service",
        provider="OpenAI",
        description="text-embedding-3-small",
        endpoint="https://api.openai.com/v1",
        api_key="test-key-123",
    )
    db_session.add(service)
    db_session.commit()
    db_session.refresh(service)
    return service


@pytest.fixture
def output_parser(db_session: Session, test_app_id: int) -> OutputParser:
    """Create test output parser."""
    parser = OutputParser(
        app_id=test_app_id,
        name="Test Parser",
        description="Test parser for metadata",
        fields=[
            {"name": "title", "type": "str", "description": "Document title"},
            {"name": "tags", "type": "list", "description": "Document tags"},
        ],
    )
    db_session.add(parser)
    db_session.commit()
    db_session.refresh(parser)
    return parser


@pytest.fixture
def test_silo(
    db_session: Session,
    test_app_id: int,
    embedding_service: EmbeddingService,
    output_parser: OutputParser,
) -> Silo:
    """Create test silo with dependencies."""
    silo = Silo(
        app_id=test_app_id,
        name="Test Silo",
        silo_type="CUSTOM",
        vector_db_type="PGVECTOR",
        embedding_service_id=embedding_service.service_id,
        metadata_definition_id=output_parser.parser_id,
        fixed_metadata=True,
        description="Test silo description",
        status="active",
    )
    db_session.add(silo)
    db_session.commit()
    db_session.refresh(silo)
    return silo


def test_export_silo_success(
    db_session: Session, test_silo: Silo, test_app_id: int, test_user_id: int
):
    """Test successful silo export."""
    export_service = SiloExportService(db_session)
    
    export_data = export_service.export_silo(
        test_silo.silo_id, test_app_id, test_user_id, include_dependencies=True
    )
    
    # Verify metadata
    assert export_data.metadata.export_version == "1.0.0"
    assert export_data.metadata.exported_by == str(test_user_id)
    assert export_data.metadata.source_app_id == test_app_id
    
    # Verify silo data
    assert export_data.silo.name == "Test Silo"
    assert export_data.silo.type == "CUSTOM"
    assert export_data.silo.vector_db_type == "PGVECTOR"
    assert export_data.silo.embedding_service_name == "Test Embedding Service"
    assert export_data.silo.metadata_definition_name == "Test Parser"
    assert export_data.silo.fixed_metadata is True
    assert export_data.silo.description == "Test silo description"
    
    # Verify dependencies bundled
    assert export_data.embedding_service is not None
    assert export_data.embedding_service.name == "Test Embedding Service"
    assert export_data.embedding_service.api_key is None  # Should be stripped
    
    assert export_data.output_parser is not None
    assert export_data.output_parser.name == "Test Parser"


def test_export_silo_without_dependencies(
    db_session: Session, test_silo: Silo, test_app_id: int
):
    """Test silo export without bundling dependencies."""
    export_service = SiloExportService(db_session)
    
    export_data = export_service.export_silo(
        test_silo.silo_id, test_app_id, include_dependencies=False
    )
    
    # Verify silo has reference names
    assert export_data.silo.embedding_service_name == "Test Embedding Service"
    assert export_data.silo.metadata_definition_name == "Test Parser"
    
    # Verify dependencies NOT bundled
    assert export_data.embedding_service is None
    assert export_data.output_parser is None


def test_export_silo_not_found(db_session: Session, test_app_id: int):
    """Test exporting non-existent silo raises error."""
    export_service = SiloExportService(db_session)
    
    with pytest.raises(ValueError, match="Silo with ID 99999 not found"):
        export_service.export_silo(99999, test_app_id)


def test_export_silo_permission_denied(db_session: Session, test_silo: Silo):
    """Test exporting silo from wrong app raises error."""
    export_service = SiloExportService(db_session)
    
    wrong_app_id = 999
    with pytest.raises(ValueError, match="permission denied"):
        export_service.export_silo(test_silo.silo_id, wrong_app_id)


def test_import_silo_new(db_session: Session, test_app_id: int, embedding_service: EmbeddingService):
    """Test importing new silo with bundled embedding service."""
    export_data = SiloExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
        ),
        silo=ExportSiloSchema(
            name="Imported Silo",
            type="REPO",
            vector_db_type="QDRANT",
            embedding_service_name="Test Embedding Service",
            fixed_metadata=False,
            description="Imported from another system",
        ),
    )
    
    import_service = SiloImportService(db_session)
    
    # Import with selected embedding service
    summary = import_service.import_silo(
        export_data,
        test_app_id,
        ConflictMode.FAIL,
        selected_embedding_service_id=embedding_service.service_id,
    )
    
    assert summary.created is True
    assert summary.component_name == "Imported Silo"
    assert "Upload documents" in " ".join(summary.next_steps)
    
    # Verify silo created in database
    silo_repo = SiloRepository()
    silo = silo_repo.get_by_id(summary.component_id, db_session)
    assert silo is not None
    assert silo.name == "Imported Silo"
    assert silo.silo_type == "REPO"
    assert silo.vector_db_type == "QDRANT"
    assert silo.embedding_service_id == embedding_service.service_id
    assert silo.fixed_metadata is False


def test_import_silo_conflict_fail(
    db_session: Session, test_silo: Silo, test_app_id: int
):
    """Test import with FAIL mode when silo exists."""
    export_data = SiloExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
        ),
        silo=ExportSiloSchema(
            name="Test Silo",  # Same name as existing
            type="CUSTOM",
            vector_db_type="PGVECTOR",
        ),
    )
    
    import_service = SiloImportService(db_session)
    
    with pytest.raises(ValueError, match="already exists"):
        import_service.import_silo(export_data, test_app_id, ConflictMode.FAIL)


def test_import_silo_conflict_rename(
    db_session: Session, test_silo: Silo, test_app_id: int, embedding_service: EmbeddingService
):
    """Test import with RENAME mode when silo exists."""
    export_data = SiloExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
        ),
        silo=ExportSiloSchema(
            name="Test Silo",  # Same name as existing
            type="DOMAIN",
            vector_db_type="QDRANT",
            embedding_service_name="Test Embedding Service",
        ),
    )
    
    import_service = SiloImportService(db_session)
    
    summary = import_service.import_silo(
        export_data,
        test_app_id,
        ConflictMode.RENAME,
        selected_embedding_service_id=embedding_service.service_id,
    )
    
    assert summary.created is True
    assert "imported" in summary.component_name.lower()
    assert summary.component_name != "Test Silo"
    
    # Verify both silos exist
    silo_repo = SiloRepository()
    silos = silo_repo.get_by_app_id(test_app_id, db_session)
    assert len(silos) == 2


def test_import_silo_conflict_override(
    db_session: Session, test_silo: Silo, test_app_id: int, embedding_service: EmbeddingService
):
    """Test import with OVERRIDE mode preserves vectors."""
    original_silo_id = test_silo.silo_id
    
    export_data = SiloExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
        ),
        silo=ExportSiloSchema(
            name="Test Silo",  # Same name
            type="DOMAIN",  # Different type
            vector_db_type="QDRANT",  # Different DB type
            embedding_service_name="Test Embedding Service",
            description="Updated description",
        ),
    )
    
    import_service = SiloImportService(db_session)
    
    summary = import_service.import_silo(
        export_data,
        test_app_id,
        ConflictMode.OVERRIDE,
        selected_embedding_service_id=embedding_service.service_id,
    )
    
    assert summary.created is False
    assert summary.component_id == original_silo_id
    assert "preserved" in " ".join(summary.warnings).lower()
    
    # Verify silo updated
    silo_repo = SiloRepository()
    silo = silo_repo.get_by_id(original_silo_id, db_session)
    assert silo.silo_type == "DOMAIN"
    assert silo.vector_db_type == "QDRANT"
    assert silo.description == "Updated description"


def test_import_silo_requires_embedding_service_selection(
    db_session: Session, test_app_id: int
):
    """Test import validation when embedding service is not bundled."""
    export_data = SiloExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
        ),
        silo=ExportSiloSchema(
            name="Silo Needs Service",
            type="CUSTOM",
            vector_db_type="PGVECTOR",
            embedding_service_name="Missing Service",  # Not bundled
        ),
    )
    
    import_service = SiloImportService(db_session)
    
    # Validate should flag requirement
    validation = import_service.validate_import(export_data, test_app_id)
    assert validation.requires_embedding_service_selection is True
    assert len(validation.warnings) > 0
    
    # Import without selection should fail
    with pytest.raises(ValueError, match="Embedding service selection required"):
        import_service.import_silo(export_data, test_app_id, ConflictMode.FAIL)


def test_import_silo_with_bundled_embedding_service(
    db_session: Session, test_app_id: int
):
    """Test import with bundled embedding service creates both."""
    export_data = SiloExportFileSchema(
        metadata=ExportMetadataSchema(
            export_version="1.0.0",
            export_date=datetime.now(),
        ),
        silo=ExportSiloSchema(
            name="Silo with Bundled Service",
            type="CUSTOM",
            vector_db_type="PGVECTOR",
            embedding_service_name="Bundled Service",
        ),
        embedding_service=ExportEmbeddingServiceSchema(
            name="Bundled Service",
            provider="Ollama",
            model_name="nomic-embed-text",
            api_key=None,
            endpoint="http://localhost:11434",
        ),
    )
    
    import_service = SiloImportService(db_session)
    
    summary = import_service.import_silo(
        export_data, test_app_id, ConflictMode.FAIL
    )
    
    assert summary.created is True
    assert len(summary.dependencies_created) == 1
    assert "Embedding Service" in summary.dependencies_created[0]
    
    # Verify silo created with new embedding service
    silo_repo = SiloRepository()
    silo = silo_repo.get_by_id(summary.component_id, db_session)
    assert silo.embedding_service is not None
    assert silo.embedding_service.name == "Bundled Service"


def test_export_import_round_trip(
    db_session: Session, test_silo: Silo, test_app_id: int
):
    """Test full export→import cycle."""
    # Export
    export_service = SiloExportService(db_session)
    export_data = export_service.export_silo(
        test_silo.silo_id, test_app_id, include_dependencies=True
    )
    
    # Modify name to avoid conflict
    export_data.silo.name = "Imported Copy"
    
    # Import
    import_service = SiloImportService(db_session)
    summary = import_service.import_silo(
        export_data, test_app_id, ConflictMode.FAIL
    )
    
    # Verify imported silo matches original
    silo_repo = SiloRepository()
    imported_silo = silo_repo.get_by_id(summary.component_id, db_session)
    
    assert imported_silo.name == "Imported Copy"
    assert imported_silo.silo_type == test_silo.silo_type
    assert imported_silo.vector_db_type == test_silo.vector_db_type
    assert imported_silo.fixed_metadata == test_silo.fixed_metadata
    # Bundled dependencies are imported with renamed names, creating new IDs
    assert imported_silo.embedding_service.name.startswith(test_silo.embedding_service.name)
    assert imported_silo.metadata_definition.name.startswith(test_silo.metadata_definition.name)
