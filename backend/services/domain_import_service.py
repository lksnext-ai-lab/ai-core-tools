"""Service for importing Domains."""

from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session

from models.domain import Domain
from models.url import Url
from models.silo import Silo
from schemas.export_schemas import DomainExportFileSchema
from schemas.import_schemas import (
    ConflictMode,
    ValidateImportResponseSchema,
    ImportSummarySchema,
    ComponentType,
)
from core.export_constants import validate_export_version
from services.silo_import_service import SiloImportService
from schemas.export_schemas import SiloExportFileSchema
import logging

logger = logging.getLogger(__name__)


class DomainImportService:
    """Service for importing Domains (structure + URLs)."""

    def __init__(self, session: Session):
        """Initialize Domain import service.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.silo_import = SiloImportService(session)

    def get_by_name_and_app(
        self, name: str, app_id: int
    ) -> Optional[Domain]:
        """Get Domain by name and app ID.

        Args:
            name: Domain name
            app_id: App ID

        Returns:
            Optional[Domain]: Domain if found
        """
        return (
            self.session.query(Domain)
            .filter(
                Domain.name == name,
                Domain.app_id == app_id,
            )
            .first()
        )

    def validate_import(
        self,
        export_data: DomainExportFileSchema,
        app_id: int,
    ) -> ValidateImportResponseSchema:
        """Validate Domain import without importing.

        Args:
            export_data: Parsed export file
            app_id: Target app ID

        Returns:
            ValidateImportResponseSchema: Validation result
        """
        validate_export_version(
            export_data.metadata.export_version
        )

        existing = self.get_by_name_and_app(
            export_data.domain.name, app_id
        )

        warnings = []
        missing_deps = []
        requires_embedding = False

        # Check silo dependency
        if export_data.domain.silo_name:
            if export_data.silo is None:
                existing_silo = (
                    self.session.query(Silo)
                    .filter(
                        Silo.name
                        == export_data.domain.silo_name,
                        Silo.app_id == app_id,
                    )
                    .first()
                )
                if not existing_silo:
                    missing_deps.append(
                        f"Silo: '{export_data.domain.silo_name}'"
                    )
                    warnings.append(
                        f"Silo '{export_data.domain.silo_name}'"
                        f" not found and not bundled."
                    )
            else:
                if (
                    export_data.silo.embedding_service_name
                    and export_data.embedding_service is None
                ):
                    requires_embedding = True
                    warnings.append(
                        "Embedding service "
                        f"'{export_data.silo.embedding_service_name}'"
                        " not bundled. You must select an "
                        "existing embedding service."
                    )

        url_count = len(export_data.domain.urls)
        warnings.append(
            f"Domain structure with {url_count} URL(s). "
            "URLs will need to be re-crawled after import."
        )

        return ValidateImportResponseSchema(
            component_type=ComponentType.DOMAIN,
            component_name=export_data.domain.name,
            has_conflict=existing is not None,
            warnings=warnings,
            missing_dependencies=missing_deps,
            requires_embedding_service_selection=requires_embedding,
        )

    def import_domain(
        self,
        export_data: DomainExportFileSchema,
        app_id: int,
        conflict_mode: ConflictMode = ConflictMode.FAIL,
        new_name: Optional[str] = None,
        selected_embedding_service_id: Optional[int] = None,
        silo_id_map: Optional[dict] = None,
        embedding_service_id_map: Optional[dict] = None,
        output_parser_id_map: Optional[dict] = None,
    ) -> ImportSummarySchema:
        """Import Domain (structure + URLs, no crawled content).

        Args:
            export_data: Parsed export file
            app_id: Target app ID
            conflict_mode: How to handle name conflicts
            new_name: Optional custom name (for rename mode)
            selected_embedding_service_id: User-selected
                embedding service
            silo_id_map: Mapping of silo names to new IDs
            embedding_service_id_map: Mapping of embedding
                service names to new IDs
            output_parser_id_map: Mapping of output parser
                names to new IDs

        Returns:
            ImportSummarySchema: Import operation summary

        Raises:
            ValueError: On conflict with FAIL mode or missing deps
        """
        # Resolve silo
        silo_id = self._resolve_silo(
            export_data,
            app_id,
            silo_id_map,
            selected_embedding_service_id,
            embedding_service_id_map,
            output_parser_id_map,
            conflict_mode=conflict_mode,
        )

        # Handle conflict
        final_name = export_data.domain.name
        existing = self.get_by_name_and_app(final_name, app_id)
        conflict_detected = existing is not None

        if existing:
            if conflict_mode == ConflictMode.FAIL:
                raise ValueError(
                    f"Domain '{final_name}' already "
                    f"exists in app {app_id}"
                )
            elif conflict_mode == ConflictMode.RENAME:
                final_name = self._generate_unique_name(
                    new_name or final_name, app_id
                )
            elif conflict_mode == ConflictMode.OVERRIDE:
                # Update existing domain
                existing.description = (
                    export_data.domain.description
                )
                existing.base_url = export_data.domain.base_url
                existing.content_tag = (
                    export_data.domain.content_tag
                )
                existing.content_class = (
                    export_data.domain.content_class
                )
                existing.content_id = (
                    export_data.domain.content_id
                )
                if silo_id:
                    existing.silo_id = silo_id

                self.session.add(existing)
                self.session.commit()

                logger.info(
                    f"Overridden domain '{existing.name}'"
                )
                return ImportSummarySchema(
                    component_type=ComponentType.DOMAIN,
                    component_id=existing.domain_id,
                    component_name=existing.name,
                    mode=conflict_mode,
                    created=False,
                    conflict_detected=True,
                    warnings=[
                        "Existing crawled content preserved"
                    ],
                    next_steps=[],
                )

        # Create new domain
        new_domain = Domain(
            name=final_name,
            description=export_data.domain.description,
            base_url=export_data.domain.base_url,
            content_tag=export_data.domain.content_tag,
            content_class=export_data.domain.content_class,
            content_id=export_data.domain.content_id,
            app_id=app_id,
            silo_id=silo_id,
            create_date=datetime.now(),
        )

        self.session.add(new_domain)
        self.session.flush()
        self.session.refresh(new_domain)

        # Create URL records (pending status — not yet crawled)
        url_count = 0
        for url_data in export_data.domain.urls:
            url_obj = Url(
                url=url_data.url,
                domain_id=new_domain.domain_id,
                status="pending",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            self.session.add(url_obj)
            url_count += 1

        if url_count > 0:
            self.session.flush()

        self.session.commit()

        logger.info(
            f"Imported Domain '{final_name}' "
            f"(ID: {new_domain.domain_id}) - "
            f"{url_count} URLs created (pending)"
        )

        return ImportSummarySchema(
            component_type=ComponentType.DOMAIN,
            component_id=new_domain.domain_id,
            component_name=new_domain.name,
            mode=conflict_mode,
            created=True,
            conflict_detected=conflict_detected,
            warnings=[],
            next_steps=[
                f"Re-crawl {url_count} URL(s) to index content",
                "Configure embedding service API key "
                "if not already set",
            ],
        )

    def _resolve_silo(
        self,
        export_data: DomainExportFileSchema,
        app_id: int,
        silo_id_map: Optional[dict],
        selected_embedding_service_id: Optional[int],
        embedding_service_id_map: Optional[dict],
        output_parser_id_map: Optional[dict],
        conflict_mode: ConflictMode = ConflictMode.RENAME,
    ) -> Optional[int]:
        """Resolve silo dependency for domain.

        Priority:
        1. Silo ID map (from full app import)
        2. Existing silo by name
        3. Bundled silo (import it)

        Returns:
            Optional[int]: Resolved silo_id
        """
        silo_name = export_data.domain.silo_name
        if not silo_name:
            return None

        # Priority 1: ID map from full app import
        if silo_id_map and silo_name in silo_id_map:
            silo_id = silo_id_map[silo_name]
            logger.info(
                f"Resolved silo via ID map: "
                f"'{silo_name}' -> ID {silo_id}"
            )
            return silo_id

        # Priority 2: Existing silo by name
        existing_silo = (
            self.session.query(Silo)
            .filter(
                Silo.name == silo_name,
                Silo.app_id == app_id,
            )
            .first()
        )
        if existing_silo:
            logger.info(
                f"Resolved silo by name: '{silo_name}'"
            )
            return existing_silo.silo_id

        # Priority 3: Bundled silo — import it
        if export_data.silo:
            silo_file = SiloExportFileSchema(
                metadata=export_data.metadata,
                silo=export_data.silo,
                embedding_service=export_data.embedding_service,
                output_parser=export_data.output_parser,
            )
            result = self.silo_import.import_silo(
                export_data=silo_file,
                app_id=app_id,
                conflict_mode=conflict_mode,
                selected_embedding_service_id=(
                    selected_embedding_service_id
                ),
                embedding_service_id_map=embedding_service_id_map,
                output_parser_id_map=output_parser_id_map,
            )
            logger.info(
                f"Imported bundled silo "
                f"'{result.component_name}'"
            )
            return result.component_id

        logger.warning(
            f"Could not resolve silo '{silo_name}' "
            f"for domain"
        )
        return None

    def _generate_unique_name(
        self, base_name: str, app_id: int
    ) -> str:
        """Generate a unique domain name.

        Args:
            base_name: Starting name
            app_id: App ID

        Returns:
            str: Unique name
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        final_name = f"{base_name} (imported {date_str})"
        counter = 1
        while self.get_by_name_and_app(final_name, app_id):
            final_name = (
                f"{base_name} (imported {date_str} {counter})"
            )
            counter += 1
        return final_name
