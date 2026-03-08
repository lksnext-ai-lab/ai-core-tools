"""Service for exporting Domains."""

from typing import Optional
from sqlalchemy.orm import Session
from schemas.export_schemas import (
    ExportDomainSchema,
    ExportDomainUrlSchema,
    DomainExportFileSchema,
)
from services.base_export_service import BaseExportService
from services.silo_export_service import SiloExportService
from repositories.domain_repository import DomainRepository
import logging

logger = logging.getLogger(__name__)


class DomainExportService(BaseExportService):
    """Service for exporting Domains (structure + URLs only)."""

    def __init__(self, session: Session):
        """Initialize Domain export service.

        Args:
            session: SQLAlchemy database session
        """
        super().__init__(session)

    def export_domain(
        self,
        domain_id: int,
        app_id: int,
        user_id: Optional[int] = None,
        include_dependencies: bool = True,
    ) -> DomainExportFileSchema:
        """Export Domain to JSON structure.

        Note: Exports domain structure and URL list only.
        Crawled content is NOT exported (heavy data).
        URLs will need to be re-crawled after import.

        Args:
            domain_id: ID of domain to export
            app_id: App ID (for permission check)
            user_id: User ID (for metadata, optional)
            include_dependencies: If True, bundle silo with
                its embedding service and output parser

        Returns:
            DomainExportFileSchema: Export file structure

        Raises:
            ValueError: If domain not found or permission denied
        """
        # Load domain
        domain = DomainRepository.get_by_id(domain_id, self.session)
        if not domain:
            raise ValueError(
                f"Domain with ID {domain_id} not found"
            )

        # Permission check
        if domain.app_id != app_id:
            raise ValueError(
                f"Domain {domain_id} does not belong to "
                f"app {app_id} (permission denied)"
            )

        # Get silo name reference
        silo_name = None
        if domain.silo:
            silo_name = domain.silo.name

        # Collect URLs (structure only, no crawled content)
        urls = []
        if hasattr(domain, "urls") and domain.urls:
            for url_obj in domain.urls:
                urls.append(
                    ExportDomainUrlSchema(url=url_obj.url)
                )

        # Create export schema
        export_domain = ExportDomainSchema(
            name=domain.name,
            description=domain.description,
            base_url=domain.base_url,
            content_tag=domain.content_tag,
            content_class=domain.content_class,
            content_id=domain.content_id,
            silo_name=silo_name,
            urls=urls,
        )

        # Optionally bundle silo with dependencies
        bundled_silo = None
        bundled_embedding_service = None
        bundled_output_parser = None

        if include_dependencies and domain.silo_id:
            try:
                silo_export = SiloExportService(self.session)
                silo_export_file = silo_export.export_silo(
                    domain.silo_id,
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
                    f"Failed to bundle silo for domain "
                    f"{domain_id}: {e}"
                )

        # Create export file
        export_file = DomainExportFileSchema(
            metadata=self.create_metadata(user_id, app_id),
            domain=export_domain,
            silo=bundled_silo,
            embedding_service=bundled_embedding_service,
            output_parser=bundled_output_parser,
        )

        logger.info(
            f"Exported Domain '{domain.name}' "
            f"(ID: {domain_id}) - "
            f"{len(urls)} URLs, crawled content excluded"
        )
        return export_file
