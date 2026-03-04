"""
Integration tests for Output Parser Export/Import with real PostgreSQL database.

These tests require:
- PostgreSQL running (docker compose up -d postgres)
- Database configured in .env
- Valid database connection

Usage:
    pytest backend/tests/test_output_parser_export_import_integration.py -v -m integration

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
from models.output_parser import OutputParser
from models.app import App
from services.output_parser_export_service import OutputParserExportService
from services.output_parser_import_service import OutputParserImportService
from schemas.export_schemas import OutputParserExportFileSchema
from schemas.import_schemas import ConflictMode, ComponentType


# ==================== FIXTURES ====================


@pytest.fixture(scope="function")
def test_app(db_session: Session):
    """Create a test app for testing."""
    # Check if app exists
    app = (
        db_session.query(App)
        .filter(App.name == "Test App Parser Export")
        .first()
    )

    if not app:
        app = App(name="Test App Parser Export", slug="test-app-parser-export")
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        created = True
    else:
        created = False

    yield app

    # Cleanup: Delete test parsers first to avoid foreign key issues
    if created:
        db_session.query(OutputParser).filter(
            OutputParser.app_id == app.app_id
        ).delete()
        db_session.commit()

    # Cleanup only if we created it
    if created:
        db_session.delete(app)
        db_session.commit()


@pytest.fixture(scope="function")
def sample_output_parser(db_session: Session, test_app: App):
    """Create a sample output parser for testing."""
    parser = OutputParser(
        app_id=test_app.app_id,
        name=f"Test Parser {datetime.now().timestamp()}",
        description="Test parser for export/import",
        fields=[
            {
                "name": "username",
                "type": "str",
                "description": "User's username"
            },
            {
                "name": "age",
                "type": "int",
                "description": "User's age"
            },
            {
                "name": "email",
                "type": "str",
                "description": "User's email address"
            }
        ],
        create_date=datetime.now()
    )
    db_session.add(parser)
    db_session.commit()
    db_session.refresh(parser)

    yield parser

    # Cleanup
    try:
        db_session.delete(parser)
        db_session.commit()
    except Exception:
        db_session.rollback()


# ==================== INTEGRATION TESTS ====================


@pytest.mark.integration
class TestOutputParserExportIntegration:
    """Integration tests for Output Parser export with real database."""

    def test_export_output_parser_success(
        self, db_session: Session, sample_output_parser: OutputParser
    ):
        """Test successful export of output parser from database."""
        export_service = OutputParserExportService(db_session)

        export_data = export_service.export_output_parser(
            sample_output_parser.parser_id,
            sample_output_parser.app_id,
            user_id=1,
        )

        # Verify export structure
        assert isinstance(export_data, OutputParserExportFileSchema)
        
        # Verify metadata
        assert export_data.metadata.export_version == "1.0.0"
        assert export_data.metadata.exported_by == "1"
        assert export_data.metadata.source_app_id == sample_output_parser.app_id
        assert export_data.metadata.export_date is not None
        
        # Verify parser data
        assert export_data.output_parser.name == sample_output_parser.name
        assert export_data.output_parser.description == sample_output_parser.description
        assert len(export_data.output_parser.fields) == 3
        
        # Verify fields
        field_names = [f.name for f in export_data.output_parser.fields]
        assert "username" in field_names
        assert "age" in field_names
        assert "email" in field_names

    def test_export_parser_not_found(self, db_session: Session, test_app: App):
        """Test export with non-existent parser ID."""
        export_service = OutputParserExportService(db_session)

        with pytest.raises(ValueError, match="not found"):
            export_service.export_output_parser(
                parser_id=999999,
                app_id=test_app.app_id,
                user_id=1
            )

    def test_export_preserves_field_structure(
        self, db_session: Session, test_app: App
    ):
        """Test that export preserves complex field structures."""
        # Create referenced parsers for parser-type fields
        address_parser = OutputParser(
            app_id=test_app.app_id,
            name=f"Address Parser {datetime.now().timestamp()}",
            description="Address parser",
            fields=[],
            create_date=datetime.now()
        )
        db_session.add(address_parser)
        db_session.flush()

        contact_parser = OutputParser(
            app_id=test_app.app_id,
            name=f"Contact Parser {datetime.now().timestamp()}",
            description="Contact parser",
            fields=[],
            create_date=datetime.now()
        )
        db_session.add(contact_parser)
        db_session.flush()

        # Create parser with complex fields referencing the above parsers
        parser = OutputParser(
            app_id=test_app.app_id,
            name=f"Complex Parser {datetime.now().timestamp()}",
            description="Parser with complex field types",
            fields=[
                {
                    "name": "tags",
                    "type": "list",
                    "description": "List of tags",
                    "list_item_type": "str"
                },
                {
                    "name": "address",
                    "type": "parser",
                    "description": "Address object",
                    "parser_id": address_parser.parser_id
                },
                {
                    "name": "contacts",
                    "type": "list",
                    "description": "List of contacts",
                    "list_item_type": "parser",
                    "list_item_parser_id": contact_parser.parser_id
                }
            ],
            create_date=datetime.now()
        )
        db_session.add(parser)
        db_session.commit()
        db_session.refresh(parser)

        # Export
        export_service = OutputParserExportService(db_session)
        export_data = export_service.export_output_parser(
            parser.parser_id,
            test_app.app_id,
            user_id=1
        )

        # Verify complex fields preserved
        assert len(export_data.output_parser.fields) == 3

        # Check list field
        list_field = next(f for f in export_data.output_parser.fields if f.name == "tags")
        assert list_field.type == "list"
        assert list_field.list_item_type == "str"

        # Check parser reference field - resolved to name
        parser_field = next(f for f in export_data.output_parser.fields if f.name == "address")
        assert parser_field.type == "parser"
        assert parser_field.parser_name == address_parser.name

        # Check list of parsers field - resolved to name
        list_parser_field = next(f for f in export_data.output_parser.fields if f.name == "contacts")
        assert list_parser_field.type == "list"
        assert list_parser_field.list_item_type == "parser"
        assert list_parser_field.list_item_parser_name == contact_parser.name

        # Cleanup
        db_session.delete(parser)
        db_session.delete(address_parser)
        db_session.delete(contact_parser)
        db_session.commit()


@pytest.mark.integration
class TestOutputParserImportIntegration:
    """Integration tests for Output Parser import with real database."""

    def test_import_new_parser_success(
        self, db_session: Session, test_app: App
    ):
        """Test importing new parser (no conflict)."""
        # Create export data
        export_data = OutputParserExportFileSchema(
            metadata={
                "export_version": "1.0.0",
                "export_date": datetime.now(),
                "exported_by": "1",
                "source_app_id": test_app.app_id
            },
            output_parser={
                "name": f"Imported Parser {datetime.now().timestamp()}",
                "description": "Imported parser for testing",
                "fields": [
                    {
                        "name": "field1",
                        "type": "str",
                        "description": "First field"
                    },
                    {
                        "name": "field2",
                        "type": "int",
                        "description": "Second field"
                    }
                ]
            }
        )

        # Import
        import_service = OutputParserImportService(db_session)
        summary = import_service.import_output_parser(
            export_data,
            test_app.app_id,
            conflict_mode=ConflictMode.FAIL
        )

        # Verify import summary
        assert summary.component_type == ComponentType.OUTPUT_PARSER
        assert summary.created is True
        assert summary.mode == ConflictMode.FAIL
        assert summary.component_name == export_data.output_parser.name

        # Verify parser in database
        imported_parser = db_session.query(OutputParser).get(summary.component_id)
        assert imported_parser is not None
        assert imported_parser.name == export_data.output_parser.name
        assert imported_parser.description == export_data.output_parser.description
        assert len(imported_parser.fields) == 2
        assert imported_parser.fields[0]["name"] == "field1"
        assert imported_parser.fields[1]["type"] == "int"

        # Cleanup
        db_session.delete(imported_parser)
        db_session.commit()

    def test_import_conflict_fail_mode(
        self, db_session: Session, sample_output_parser: OutputParser
    ):
        """Test import with name conflict in FAIL mode."""
        # Create export data with same name
        export_data = OutputParserExportFileSchema(
            metadata={
                "export_version": "1.0.0",
                "export_date": datetime.now(),
                "exported_by": "1",
                "source_app_id": sample_output_parser.app_id
            },
            output_parser={
                "name": sample_output_parser.name,
                "description": "Conflicting parser",
                "fields": []
            }
        )

        # Import should fail
        import_service = OutputParserImportService(db_session)
        with pytest.raises(ValueError, match="already exists"):
            import_service.import_output_parser(
                export_data,
                sample_output_parser.app_id,
                conflict_mode=ConflictMode.FAIL
            )

    def test_import_conflict_rename_mode(
        self, db_session: Session, sample_output_parser: OutputParser
    ):
        """Test import with name conflict in RENAME mode."""
        # Create export data with same name
        export_data = OutputParserExportFileSchema(
            metadata={
                "export_version": "1.0.0",
                "export_date": datetime.now(),
                "exported_by": "1",
                "source_app_id": sample_output_parser.app_id
            },
            output_parser={
                "name": sample_output_parser.name,
                "description": "Conflicting parser",
                "fields": [
                    {
                        "name": "new_field",
                        "type": "str",
                        "description": "A new field"
                    }
                ]
            }
        )

        # Import with RENAME mode
        import_service = OutputParserImportService(db_session)
        summary = import_service.import_output_parser(
            export_data,
            sample_output_parser.app_id,
            conflict_mode=ConflictMode.RENAME
        )

        # Verify renamed
        assert summary.created is True
        assert summary.component_name != sample_output_parser.name
        assert "(imported" in summary.component_name

        # Verify parser in database
        imported_parser = db_session.query(OutputParser).get(summary.component_id)
        assert imported_parser is not None
        assert imported_parser.name != sample_output_parser.name
        assert len(imported_parser.fields) == 1

        # Cleanup
        db_session.delete(imported_parser)
        db_session.commit()

    def test_import_conflict_rename_with_custom_name(
        self, db_session: Session, sample_output_parser: OutputParser
    ):
        """Test import with RENAME mode using custom name."""
        custom_name = f"Custom Name {datetime.now().timestamp()}"
        
        # Create export data with same name
        export_data = OutputParserExportFileSchema(
            metadata={
                "export_version": "1.0.0",
                "export_date": datetime.now(),
                "exported_by": "1",
                "source_app_id": sample_output_parser.app_id
            },
            output_parser={
                "name": sample_output_parser.name,
                "description": "Parser to rename",
                "fields": []
            }
        )

        # Import with custom name
        import_service = OutputParserImportService(db_session)
        summary = import_service.import_output_parser(
            export_data,
            sample_output_parser.app_id,
            conflict_mode=ConflictMode.RENAME,
            new_name=custom_name
        )

        # Verify custom name used
        assert summary.created is True
        assert summary.component_name == custom_name

        # Verify parser in database
        imported_parser = db_session.query(OutputParser).get(summary.component_id)
        assert imported_parser is not None
        assert imported_parser.name == custom_name

        # Cleanup
        db_session.delete(imported_parser)
        db_session.commit()

    def test_import_conflict_override_mode(
        self, db_session: Session, sample_output_parser: OutputParser
    ):
        """Test import with name conflict in OVERRIDE mode."""
        original_id = sample_output_parser.parser_id
        original_fields_count = len(sample_output_parser.fields)
        
        # Create export data with same name but different fields
        export_data = OutputParserExportFileSchema(
            metadata={
                "export_version": "1.0.0",
                "export_date": datetime.now(),
                "exported_by": "1",
                "source_app_id": sample_output_parser.app_id
            },
            output_parser={
                "name": sample_output_parser.name,
                "description": "Updated description",
                "fields": [
                    {
                        "name": "new_field_1",
                        "type": "str",
                        "description": "New field 1"
                    },
                    {
                        "name": "new_field_2",
                        "type": "bool",
                        "description": "New field 2"
                    },
                    {
                        "name": "new_field_3",
                        "type": "float",
                        "description": "New field 3"
                    }
                ]
            }
        )

        # Import with OVERRIDE mode
        import_service = OutputParserImportService(db_session)
        summary = import_service.import_output_parser(
            export_data,
            sample_output_parser.app_id,
            conflict_mode=ConflictMode.OVERRIDE
        )

        # Verify override (not created, updated)
        assert summary.created is False
        assert summary.component_id == original_id
        assert summary.component_name == sample_output_parser.name

        # Refresh from database
        db_session.refresh(sample_output_parser)

        # Verify fields updated
        assert sample_output_parser.description == "Updated description"
        assert len(sample_output_parser.fields) == 3
        assert sample_output_parser.fields[0]["name"] == "new_field_1"
        assert sample_output_parser.fields[1]["type"] == "bool"
        assert sample_output_parser.fields[2]["name"] == "new_field_3"

    def test_import_with_invalid_json(
        self, db_session: Session, test_app: App
    ):
        """Test import with invalid JSON structure."""
        # Missing required fields
        with pytest.raises(Exception):
            OutputParserExportFileSchema(
                metadata={
                    "export_version": "1.0.0",
                    "export_date": datetime.now()
                },
                output_parser={
                    # Missing 'name' field
                    "description": "Invalid parser",
                    "fields": []
                }
            )

    def test_export_import_roundtrip(
        self, db_session: Session, sample_output_parser: OutputParser
    ):
        """Test full export → import cycle preserves data."""
        # Export
        export_service = OutputParserExportService(db_session)
        export_data = export_service.export_output_parser(
            sample_output_parser.parser_id,
            sample_output_parser.app_id,
            user_id=1
        )

        # Modify name to avoid conflict
        export_data.output_parser.name = f"Roundtrip {datetime.now().timestamp()}"

        # Import
        import_service = OutputParserImportService(db_session)
        summary = import_service.import_output_parser(
            export_data,
            sample_output_parser.app_id,
            conflict_mode=ConflictMode.FAIL
        )

        # Verify imported parser matches original
        imported_parser = db_session.query(OutputParser).get(summary.component_id)
        assert imported_parser is not None
        assert imported_parser.description == sample_output_parser.description
        assert len(imported_parser.fields) == len(sample_output_parser.fields)
        
        # Verify field details
        for i, field in enumerate(imported_parser.fields):
            original_field = sample_output_parser.fields[i]
            assert field["name"] == original_field["name"]
            assert field["type"] == original_field["type"]
            assert field["description"] == original_field["description"]

        # Cleanup
        db_session.delete(imported_parser)
        db_session.commit()
