"""Service for importing Output Parsers."""

from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from models.output_parser import OutputParser
from schemas.export_schemas import OutputParserExportFileSchema
from schemas.import_schemas import (
    ConflictMode,
    ValidateImportResponseSchema,
    ImportSummarySchema,
    ComponentType,
)
from core.export_constants import validate_export_version
from repositories.output_parser_repository import OutputParserRepository
import logging

logger = logging.getLogger(__name__)


class OutputParserImportService:
    """Service for importing Output Parsers."""

    def __init__(self, session: Session):
        """Initialize Output Parser import service.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.output_parser_repo = OutputParserRepository()

    def get_by_name_and_app(self, name: str, app_id: int) -> Optional[OutputParser]:
        """Get Output Parser by name and app ID.

        Args:
            name: Parser name
            app_id: App ID

        Returns:
            Optional[OutputParser]: Parser if found, None otherwise
        """
        return (
            self.session.query(OutputParser)
            .filter(OutputParser.name == name, OutputParser.app_id == app_id)
            .first()
        )

    def validate_import(
        self, export_data: OutputParserExportFileSchema, app_id: int
    ) -> ValidateImportResponseSchema:
        """Validate Output Parser import without importing.

        Args:
            export_data: Parsed export file
            app_id: Target app ID

        Returns:
            ValidateImportResponseSchema: Validation result
        """
        # Validate version
        validate_export_version(export_data.metadata.export_version)

        # Check for name conflict
        existing_parser = self.get_by_name_and_app(
            export_data.output_parser.name, app_id
        )

        return ValidateImportResponseSchema(
            component_type=ComponentType.OUTPUT_PARSER,
            component_name=export_data.output_parser.name,
            has_conflict=existing_parser is not None,
            warnings=[],
            missing_dependencies=[],  # Output Parsers have no external dependencies
        )

    def import_output_parser(
        self,
        export_data: OutputParserExportFileSchema,
        app_id: int,
        conflict_mode: ConflictMode = ConflictMode.FAIL,
        new_name: Optional[str] = None,
    ) -> ImportSummarySchema:
        """Import Output Parser.

        Args:
            export_data: Parsed export file
            app_id: Target app ID
            conflict_mode: How to handle name conflicts
            new_name: Optional custom name (for rename mode)

        Returns:
            ImportSummarySchema: Import operation summary

        Raises:
            ValueError: On conflict with FAIL mode
        """
        # Validate
        validation = self.validate_import(export_data, app_id)

        # Handle conflict
        final_name = export_data.output_parser.name
        existing_parser = self.get_by_name_and_app(final_name, app_id)

        if existing_parser:
            if conflict_mode == ConflictMode.FAIL:
                raise ValueError(
                    f"Output Parser '{final_name}' already exists in app {app_id}"
                )
            elif conflict_mode == ConflictMode.RENAME:
                if new_name:
                    final_name = new_name
                else:
                    date_str = datetime.now().strftime("%Y-%m-%d")
                    final_name = f"{final_name} (imported {date_str})"

                    # Ensure uniqueness
                    counter = 1
                    while self.get_by_name_and_app(final_name, app_id):
                        final_name = f"{export_data.output_parser.name} (imported {date_str} {counter})"
                        counter += 1
            elif conflict_mode == ConflictMode.OVERRIDE:
                # Update existing parser
                existing_parser.description = export_data.output_parser.description

                # Convert fields from export schema to JSON
                fields_json = []
                for field in export_data.output_parser.fields:
                    field_dict = {
                        "name": field.name,
                        "type": field.type,
                        "description": field.description,
                    }
                    if field.parser_id is not None:
                        field_dict["parser_id"] = field.parser_id
                    if field.list_item_type is not None:
                        field_dict["list_item_type"] = field.list_item_type
                    if field.list_item_parser_id is not None:
                        field_dict["list_item_parser_id"] = field.list_item_parser_id
                    fields_json.append(field_dict)

                existing_parser.fields = fields_json

                self.session.add(existing_parser)
                self.session.flush()

                return ImportSummarySchema(
                    component_type=ComponentType.OUTPUT_PARSER,
                    component_id=existing_parser.parser_id,
                    component_name=existing_parser.name,
                    mode=conflict_mode,
                    created=False,
                    conflict_detected=True,
                    warnings=[],
                    next_steps=[
                        "Review and test the imported parser schema",
                        "Update agents or services using this parser",
                    ],
                )

        # Convert fields from export schema to JSON
        fields_json = []
        for field in export_data.output_parser.fields:
            field_dict = {
                "name": field.name,
                "type": field.type,
                "description": field.description,
            }
            if field.parser_id is not None:
                field_dict["parser_id"] = field.parser_id
            if field.list_item_type is not None:
                field_dict["list_item_type"] = field.list_item_type
            if field.list_item_parser_id is not None:
                field_dict["list_item_parser_id"] = field.list_item_parser_id
            fields_json.append(field_dict)

        # Create new parser
        new_parser = OutputParser(
            app_id=app_id,
            name=final_name,
            description=export_data.output_parser.description,
            fields=fields_json,
            create_date=datetime.now(),
        )

        self.session.add(new_parser)
        self.session.commit()
        self.session.refresh(new_parser)

        logger.info(
            f"Imported Output Parser '{final_name}' (ID: {new_parser.parser_id})"
        )

        return ImportSummarySchema(
            component_type=ComponentType.OUTPUT_PARSER,
            component_id=new_parser.parser_id,
            component_name=new_parser.name,
            mode=conflict_mode,
            created=True,
            conflict_detected=existing_parser is not None,
            warnings=[],
            next_steps=[
                "Review and test the imported parser schema",
                "Update agents or services using this parser",
            ],
        )
