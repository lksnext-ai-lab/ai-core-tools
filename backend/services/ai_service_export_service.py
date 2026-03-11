"""Service for exporting AI Services."""

from typing import Optional
from sqlalchemy.orm import Session
from models.ai_service import AIService
from schemas.export_schemas import (
    ExportAIServiceSchema,
    AIServiceExportFileSchema,
)
from services.base_export_service import BaseExportService
from repositories.ai_service_repository import AIServiceRepository
import logging

logger = logging.getLogger(__name__)


class AIServiceExportService(BaseExportService):
    """Service for exporting AI Services."""

    def __init__(self, session: Session):
        """Initialize AI Service export service.

        Args:
            session: SQLAlchemy database session
        """
        super().__init__(session)
        self.ai_service_repo = AIServiceRepository()

    def export_ai_service(
        self, service_id: int, app_id: int, user_id: Optional[int] = None
    ) -> AIServiceExportFileSchema:
        """Export AI Service to JSON structure.

        Args:
            service_id: ID of AI service to export
            app_id: App ID (for permission check)
            user_id: User ID (for permission check, optional)

        Returns:
            AIServiceExportFileSchema: Export file structure

        Raises:
            ValueError: If service not found or permission denied
        """
        # Load service
        service = self.ai_service_repo.get_by_id_and_app_id(
            self.session, service_id, app_id
        )
        if not service:
            raise ValueError(
                f"AI Service with ID {service_id} not found in app {app_id}"
            )

        # Create export schema (CRITICAL: Always strip API key for security)
        export_service = ExportAIServiceSchema(
            name=service.name,
            api_key=None,  # CRITICAL: Always strip API key
            provider=service.provider,
            model_name=service.description,  # BD: description field stores model_name
            endpoint=service.endpoint,  # BD: endpoint field stores base_url
            description=None,  # No separate description field in current model
            api_version=service.api_version,
        )

        # Create export file
        export_file = AIServiceExportFileSchema(
            metadata=self.create_metadata(user_id, app_id),
            ai_service=export_service,
        )

        logger.info(f"Exported AI Service '{service.name}' (ID: {service_id})")
        return export_file
