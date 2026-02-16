"""Service for importing Embedding Services."""

from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from models.embedding_service import EmbeddingService
from schemas.export_schemas import EmbeddingServiceExportFileSchema
from schemas.import_schemas import (
    ConflictMode,
    ValidateImportResponseSchema,
    ImportSummarySchema,
    ComponentType,
)
from core.export_constants import (
    validate_export_version,
    PLACEHOLDER_API_KEY,
)
from repositories.embedding_service_repository import (
    EmbeddingServiceRepository,
)
import logging

logger = logging.getLogger(__name__)


class EmbeddingServiceImportService:
    """Service for importing Embedding Services."""

    def __init__(self, session: Session):
        """Initialize Embedding Service import service.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.embedding_service_repo = EmbeddingServiceRepository()

    def get_by_name_and_app(
        self, name: str, app_id: int
    ) -> Optional[EmbeddingService]:
        """Get Embedding service by name and app ID.

        Args:
            name: Service name
            app_id: App ID

        Returns:
            Optional[EmbeddingService]: Service if found, None otherwise
        """
        return (
            self.session.query(EmbeddingService)
            .filter(EmbeddingService.name == name, EmbeddingService.app_id == app_id)
            .first()
        )

    def validate_import(
        self, export_data: EmbeddingServiceExportFileSchema, app_id: int
    ) -> ValidateImportResponseSchema:
        """Validate Embedding Service import without importing.

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
            export_data.embedding_service.name, app_id
        )

        warnings = []
        if export_data.embedding_service.api_key is None:
            warnings.append("API key must be configured after import")

        return ValidateImportResponseSchema(
            component_type=ComponentType.EMBEDDING_SERVICE,
            component_name=export_data.embedding_service.name,
            has_conflict=existing_service is not None,
            warnings=warnings,
            missing_dependencies=[],  # Embedding Services have no dependencies
        )

    def import_embedding_service(
        self,
        export_data: EmbeddingServiceExportFileSchema,
        app_id: int,
        conflict_mode: ConflictMode = ConflictMode.FAIL,
        new_name: Optional[str] = None,
    ) -> ImportSummarySchema:
        """Import Embedding Service.

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
        final_name = export_data.embedding_service.name
        existing_service = self.get_by_name_and_app(final_name, app_id)

        if existing_service:
            if conflict_mode == ConflictMode.FAIL:
                raise ValueError(
                    f"Embedding Service '{final_name}' already exists in app {app_id}"
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
                        final_name = f"{export_data.embedding_service.name} (imported {date_str} {counter})"
                        counter += 1
            elif conflict_mode == ConflictMode.OVERRIDE:
                # Update existing service
                existing_service.provider = export_data.embedding_service.provider
                existing_service.description = (
                    export_data.embedding_service.model_name
                )  # model_name mapped to description
                existing_service.endpoint = export_data.embedding_service.endpoint
                # Note: Keep existing api_key (user configured)

                self.session.add(existing_service)
                self.session.flush()

                return ImportSummarySchema(
                    component_type=ComponentType.EMBEDDING_SERVICE,
                    component_id=existing_service.service_id,
                    component_name=existing_service.name,
                    mode=conflict_mode,
                    created=False,
                    conflict_detected=True,
                    warnings=["Existing API key preserved"],
                    next_steps=[],
                )

        # Create new service
        new_service = EmbeddingService(
            app_id=app_id,
            name=final_name,
            api_key=PLACEHOLDER_API_KEY,  # User must configure
            provider=export_data.embedding_service.provider,
            description=export_data.embedding_service.model_name,  # model_name mapped to description
            endpoint=export_data.embedding_service.endpoint,
        )

        self.session.add(new_service)
        self.session.commit()
        self.session.refresh(new_service)

        logger.info(
            f"Imported Embedding Service '{final_name}' (ID: {new_service.service_id})"
        )

        return ImportSummarySchema(
            component_type=ComponentType.EMBEDDING_SERVICE,
            component_id=new_service.service_id,
            component_name=new_service.name,
            mode=conflict_mode,
            created=True,
            conflict_detected=existing_service is not None,
            warnings=[
                "API key set to placeholder 'CHANGE_ME' "
                "— update it before using this service"
            ],
            next_steps=[
                "Configure API key for the imported "
                "Embedding Service"
            ],
        )
