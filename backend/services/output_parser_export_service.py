"""Service for exporting Output Parsers."""

from typing import Optional
from sqlalchemy.orm import Session
from models.output_parser import OutputParser
from schemas.export_schemas import (
    ExportOutputParserSchema,
    ExportOutputParserFieldSchema,
    OutputParserExportFileSchema,
)
from services.base_export_service import BaseExportService
from repositories.output_parser_repository import OutputParserRepository
import logging

logger = logging.getLogger(__name__)


class OutputParserExportService(BaseExportService):
    """Service for exporting Output Parsers."""

    def __init__(self, session: Session):
        """Initialize Output Parser export service.

        Args:
            session: SQLAlchemy database session
        """
        super().__init__(session)
        self.output_parser_repo = OutputParserRepository()

    def export_output_parser(
        self, parser_id: int, app_id: int, user_id: Optional[int] = None
    ) -> OutputParserExportFileSchema:
        """Export Output Parser to JSON structure.

        Args:
            parser_id: ID of output parser to export
            app_id: App ID (for permission check)
            user_id: User ID (for permission check, optional)

        Returns:
            OutputParserExportFileSchema: Export file structure

        Raises:
            ValueError: If parser not found or permission denied
        """
        # Load parser
        parser = self.output_parser_repo.get_by_id_and_app_id(
            self.session, parser_id, app_id
        )
        if not parser:
            raise ValueError(
                f"Output Parser with ID {parser_id} not found in app {app_id}"
            )

        # Convert fields to export schema
        export_fields = []
        if parser.fields:
            for field_data in parser.fields:
                export_fields.append(
                    ExportOutputParserFieldSchema(
                        name=field_data.get("name", ""),
                        type=field_data.get("type", "str"),
                        description=field_data.get("description", ""),
                        parser_id=field_data.get("parser_id"),
                        list_item_type=field_data.get("list_item_type"),
                        list_item_parser_id=field_data.get("list_item_parser_id"),
                    )
                )

        # Create export schema
        export_parser = ExportOutputParserSchema(
            name=parser.name,
            description=parser.description,
            fields=export_fields,
        )

        # Create export file
        export_file = OutputParserExportFileSchema(
            metadata=self.create_metadata(user_id, app_id),
            output_parser=export_parser,
        )

        logger.info(f"Exported Output Parser '{parser.name}' (ID: {parser_id})")
        return export_file
