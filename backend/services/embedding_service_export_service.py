"""Service for exporting Embedding Services."""

from typing import Optional
from sqlalchemy.orm import Session
from models.embedding_service import EmbeddingService
from schemas.export_schemas import (
    ExportEmbeddingServiceSchema,
    EmbeddingServiceExportFileSchema,
)
from services.base_export_service import BaseExportService
from repositories.embedding_service_repository import EmbeddingServiceRepository
import logging

logger = logging.getLogger(__name__)


class EmbeddingServiceExportService(BaseExportService):
    """Service for exporting Embedding Services."""

    def __init__(self, session: Session):
        """Initialize Embedding Service export service.

        Args:
            session: SQLAlchemy database session
        """
        super().__init__(session)
        self.embedding_service_repo = EmbeddingServiceRepository()

    def export_embedding_service(
        self, service_id: int, app_id: int, user_id: Optional[int] = None
    ) -> EmbeddingServiceExportFileSchema:
        """Export Embedding Service to JSON structure.

        Args:
            service_id: ID of embedding service to export
            app_id: App ID (for permission check)
            user_id: User ID (for permission check, optional)

        Returns:
            EmbeddingServiceExportFileSchema: Export file structure

        Raises:
            ValueError: If service not found or permission denied
        """
        # Load service
        service = self.embedding_service_repo.get_by_id_and_app_id(
            self.session, service_id, app_id
        )
        if not service:
            raise ValueError(
                f"Embedding Service with ID {service_id} not found in app {app_id}"
            )

        # Create export schema (CRITICAL: Always strip API key for security)
        export_service = ExportEmbeddingServiceSchema(
            name=service.name,
            api_key=None,  # CRITICAL: Always strip API key
            provider=service.provider,
            model_name=service.description,  # BD: description field stores model_name
            endpoint=service.endpoint,  # BD: endpoint field stores base_url
            description=None,  # No separate description field in current model
        )

        # Create export file
        export_file = EmbeddingServiceExportFileSchema(
            metadata=self.create_metadata(user_id, app_id),
            embedding_service=export_service,
        )

        logger.info(
            f"Exported Embedding Service '{service.name}' (ID: {service_id})"
        )
        return export_file
