"""Service for importing AI Services."""

from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from models.ai_service import AIService
from schemas.export_schemas import AIServiceExportFileSchema
from schemas.import_schemas import (
    ConflictMode,
    ValidateImportResponseSchema,
    ImportSummarySchema,
    ComponentType,
)
from core.export_constants import validate_export_version
from repositories.ai_service_repository import AIServiceRepository
import logging

logger = logging.getLogger(__name__)


class AIServiceImportService:
    """Service for importing AI Services."""

    def __init__(self, session: Session):
        """Initialize AI Service import service.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.ai_service_repo = AIServiceRepository()

    def get_by_name_and_app(
        self, name: str, app_id: int
    ) -> Optional[AIService]:
        """Get AI service by name and app ID.

        Args:
            name: Service name
            app_id: App ID

        Returns:
            Optional[AIService]: Service if found, None otherwise
        """
        return (
            self.session.query(AIService)
            .filter(AIService.name == name, AIService.app_id == app_id)
            .first()
        )

    def validate_import(
        self, export_data: AIServiceExportFileSchema, app_id: int
    ) -> ValidateImportResponseSchema:
        """Validate AI Service import without importing.

        Args:
            export_data: Parsed export file
            app_id: Target app ID

        Returns:
            ValidateImportResponseSchema: Validation result
        """
        # Validate version
        validate_export_version(export_data.metadata.export_version)

        # Check for name conflict
        existing_service = self.get_by_name_and_app(
            export_data.ai_service.name, app_id
        )

        warnings = []
        if export_data.ai_service.api_key is None:
            warnings.append("API key must be configured after import")

        return ValidateImportResponseSchema(
            component_type=ComponentType.AI_SERVICE,
            component_name=export_data.ai_service.name,
            has_conflict=existing_service is not None,
            warnings=warnings,
            missing_dependencies=[],  # AI Services have no dependencies
        )

    def import_ai_service(
        self,
        export_data: AIServiceExportFileSchema,
        app_id: int,
        user_id: Optional[int] = None,
        conflict_mode: ConflictMode = ConflictMode.FAIL,
        new_name: Optional[str] = None,
    ) -> ImportSummarySchema:
        """Import AI Service.

        Args:
            export_data: Parsed export file
            app_id: Target app ID
            user_id: User performing import (optional)
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
        final_name = export_data.ai_service.name
        existing_service = None

        if validation.has_conflict:
            existing_service = self.get_by_name_and_app(final_name, app_id)

            if conflict_mode == ConflictMode.FAIL:
                raise ValueError(
                    f"AI Service '{final_name}' already exists in app {app_id}"
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
                        final_name = f"{export_data.ai_service.name} (imported {date_str} {counter})"
                        counter += 1
            elif conflict_mode == ConflictMode.OVERRIDE:
                # Update existing service
                existing_service.provider = export_data.ai_service.provider
                existing_service.description = export_data.ai_service.model_name  # model_name mapped to description
                existing_service.endpoint = export_data.ai_service.endpoint
                existing_service.api_version = export_data.ai_service.api_version
                # Note: Keep existing api_key (user configured)

                self.session.add(existing_service)
                self.session.commit()

                return ImportSummarySchema(
                    component_type=ComponentType.AI_SERVICE,
                    component_id=existing_service.service_id,
                    component_name=existing_service.name,
                    mode=conflict_mode,
                    created=False,
                    conflict_detected=True,
                    warnings=["Existing API key preserved"],
                    next_steps=[],
                )

        # Create new service
        new_service = AIService(
            app_id=app_id,
            name=final_name,
            api_key=None,  # User must configure
            provider=export_data.ai_service.provider,
            description=export_data.ai_service.model_name,  # model_name mapped to description
            endpoint=export_data.ai_service.endpoint,
            api_version=export_data.ai_service.api_version,
        )

        self.session.add(new_service)
        self.session.commit()
        self.session.refresh(new_service)

        logger.info(f"Imported AI Service '{final_name}' (ID: {new_service.service_id})")

        return ImportSummarySchema(
            component_type=ComponentType.AI_SERVICE,
            component_id=new_service.service_id,
            component_name=new_service.name,
            mode=conflict_mode,
            created=True,
            conflict_detected=existing_service is not None,
            warnings=[],
            next_steps=["Configure API key for the imported AI Service"],
        )
