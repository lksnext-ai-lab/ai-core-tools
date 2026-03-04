"""Service for exporting Repositories."""

from typing import Optional
from sqlalchemy.orm import Session
from schemas.export_schemas import (
    ExportRepositorySchema,
    RepositoryExportFileSchema,
)
from services.base_export_service import BaseExportService
from services.silo_export_service import SiloExportService
from repositories.repository_repository import RepositoryRepository
import logging

logger = logging.getLogger(__name__)


class RepositoryExportService(BaseExportService):
    """Service for exporting Repositories (structure only)."""

    def __init__(self, session: Session):
        """Initialize Repository export service.

        Args:
            session: SQLAlchemy database session
        """
        super().__init__(session)

    def export_repository(
        self,
        repository_id: int,
        app_id: int,
        user_id: Optional[int] = None,
        include_dependencies: bool = True,
    ) -> RepositoryExportFileSchema:
        """Export Repository to JSON structure.

        Note: Exports repository STRUCTURE only (no files/resources).
        Files must be re-uploaded after import.

        Args:
            repository_id: ID of repository to export
            app_id: App ID (for permission check)
            user_id: User ID (for metadata, optional)
            include_dependencies: If True, bundle silo with its
                embedding service and output parser

        Returns:
            RepositoryExportFileSchema: Export file structure

        Raises:
            ValueError: If repository not found or permission denied
        """
        # Load repository
        repository = RepositoryRepository.get_by_id(
            self.session, repository_id
        )
        if not repository:
            raise ValueError(
                f"Repository with ID {repository_id} not found"
            )

        # Permission check
        if repository.app_id != app_id:
            raise ValueError(
                f"Repository {repository_id} does not belong to "
                f"app {app_id} (permission denied)"
            )

        # Get silo name reference
        silo_name = None
        if repository.silo:
            silo_name = repository.silo.name

        # Create export schema
        export_repository = ExportRepositorySchema(
            name=repository.name,
            type=repository.type or "UPLOAD",
            silo_name=silo_name,
        )

        # Optionally bundle silo with dependencies
        bundled_silo = None
        bundled_embedding_service = None
        bundled_output_parser = None

        if include_dependencies and repository.silo_id:
            try:
                silo_export = SiloExportService(self.session)
                silo_export_file = silo_export.export_silo(
                    repository.silo_id,
                    app_id,
                    user_id,
                    include_dependencies=True,
                )
                bundled_silo = silo_export_file.silo
                bundled_embedding_service = (
                    silo_export_file.embedding_service
                )
                bundled_output_parser = (
                    silo_export_file.output_parser
                )
            except Exception as e:
                logger.warning(
                    f"Failed to bundle silo for repository "
                    f"{repository_id}: {e}"
                )

        # Create export file
        export_file = RepositoryExportFileSchema(
            metadata=self.create_metadata(user_id, app_id),
            repository=export_repository,
            silo=bundled_silo,
            embedding_service=bundled_embedding_service,
            output_parser=bundled_output_parser,
        )

        logger.info(
            f"Exported Repository '{repository.name}' "
            f"(ID: {repository_id}) - Structure only, "
            f"files excluded"
        )
        return export_file
