"""Base classes for export/import services."""

from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from core.export_constants import CURRENT_EXPORT_VERSION
from schemas.export_schemas import ExportMetadataSchema
import logging

logger = logging.getLogger(__name__)


class BaseExportService:
    """Base class for component export services."""

    def __init__(self, session: Session):
        """Initialize base export service.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    def create_metadata(
        self, user_id: Optional[int] = None, app_id: Optional[int] = None
    ) -> ExportMetadataSchema:
        """Create export metadata.

        Args:
            user_id: ID of user performing export (optional)
            app_id: ID of app being exported from (optional)

        Returns:
            ExportMetadataSchema: Metadata for export file
        """
        return ExportMetadataSchema(
            export_version=CURRENT_EXPORT_VERSION,
            export_date=datetime.now(),
            exported_by=str(user_id) if user_id else None,
            source_app_id=app_id,
        )

    def sanitize_secrets(self, data: dict) -> dict:
        """Remove all API keys and secrets from export data.

        Args:
            data: Dictionary containing export data

        Returns:
            dict: Sanitized data with secrets removed
        """
        if "api_key" in data:
            data["api_key"] = None
        return data
