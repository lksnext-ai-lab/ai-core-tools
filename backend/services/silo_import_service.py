"""Service for importing Silos."""

from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from models.silo import Silo
from models.embedding_service import EmbeddingService
from models.output_parser import OutputParser
from schemas.export_schemas import SiloExportFileSchema
from schemas.import_schemas import (
    ConflictMode,
    ValidateImportResponseSchema,
    ImportSummarySchema,
    ComponentType,
)
from core.export_constants import validate_export_version
from services.embedding_service_import_service import EmbeddingServiceImportService
from services.output_parser_import_service import OutputParserImportService
from repositories.silo_repository import SiloRepository
import logging

logger = logging.getLogger(__name__)


class SiloImportService:
    """Service for importing Silos (vector store structure only)."""

    def __init__(self, session: Session):
        """Initialize Silo import service.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.silo_repo = SiloRepository()
        self.embedding_service_import = EmbeddingServiceImportService(session)
        self.output_parser_import = OutputParserImportService(session)

    def get_by_name_and_app(self, name: str, app_id: int) -> Optional[Silo]:
        """Get Silo by name and app ID.

        Args:
            name: Silo name
            app_id: App ID

        Returns:
            Optional[Silo]: Silo if found, None otherwise
        """
        return (
            self.session.query(Silo)
            .filter(Silo.name == name, Silo.app_id == app_id)
            .first()
        )

    def validate_import(
        self, export_data: SiloExportFileSchema, app_id: int
    ) -> ValidateImportResponseSchema:
        """Validate Silo import without importing.

        Args:
            export_data: Parsed export file
            app_id: Target app ID

        Returns:
            ValidateImportResponseSchema: Validation result
        """
        # Validate version
        validate_export_version(export_data.metadata.export_version)

        # Check for name conflict
        existing_silo = self.get_by_name_and_app(export_data.silo.name, app_id)

        warnings = []
        missing_dependencies = []
        requires_embedding_service_selection = False

        # Check embedding service dependency
        if export_data.silo.embedding_service_name:
            # If embedding service is NOT bundled, require user selection
            if export_data.embedding_service is None:
                requires_embedding_service_selection = True
                warnings.append(
                    f"Embedding service '{export_data.silo.embedding_service_name}' "
                    f"not bundled. You must select an existing embedding service."
                )
            else:
                # Bundled - validate it can be imported
                try:
                    self.embedding_service_import.validate_import(
                        export_data, app_id
                    )
                except Exception as e:
                    warnings.append(
                        f"Bundled embedding service validation issue: {e}"
                    )

        # Check output parser dependency (optional)
        if export_data.silo.metadata_definition_name:
            if export_data.output_parser is None:
                # Not bundled - check if exists
                existing_parser = (
                    self.session.query(OutputParser)
                    .filter(
                        OutputParser.name == export_data.silo.metadata_definition_name,
                        OutputParser.app_id == app_id,
                    )
                    .first()
                )
                if not existing_parser:
                    missing_dependencies.append(
                        f"Output Parser: '{export_data.silo.metadata_definition_name}'"
                    )
                    warnings.append(
                        f"Output parser '{export_data.silo.metadata_definition_name}' "
                        f"not found. Silo will be created without metadata definition."
                    )

        # Warning about vectors
        warnings.append(
            "Silo structure only (no vector data). "
            "Upload documents to populate vectors after import."
        )

        return ValidateImportResponseSchema(
            component_type=ComponentType.SILO,
            component_name=export_data.silo.name,
            has_conflict=existing_silo is not None,
            warnings=warnings,
            missing_dependencies=missing_dependencies,
            requires_embedding_service_selection=requires_embedding_service_selection,
        )

    def import_silo(
        self,
        export_data: SiloExportFileSchema,
        app_id: int,
        conflict_mode: ConflictMode = ConflictMode.FAIL,
        new_name: Optional[str] = None,
        selected_embedding_service_id: Optional[int] = None,
        embedding_service_id_map: Optional[dict] = None,
        output_parser_id_map: Optional[dict] = None,
    ) -> ImportSummarySchema:
        """Import Silo (structure only, no vectors).

        Args:
            export_data: Parsed export file
            app_id: Target app ID
            conflict_mode: How to handle name conflicts
            new_name: Optional custom name (for rename mode)
            selected_embedding_service_id: User-selected embedding service
                (required if embedding service not bundled)
            embedding_service_id_map: Mapping of original embedding service names to new IDs
            output_parser_id_map: Mapping of original output parser names to new IDs

        Returns:
            ImportSummarySchema: Import operation summary

        Raises:
            ValueError: On conflict with FAIL mode or missing dependencies
        """
        # Validate
        validation = self.validate_import(export_data, app_id)

        # Check if embedding service selection is required
        # BUT: Skip this check if we have an ID map (from full app import)
        if validation.requires_embedding_service_selection:
            has_id_map = (
                embedding_service_id_map 
                and export_data.silo.embedding_service_name 
                and export_data.silo.embedding_service_name in embedding_service_id_map
            )
            if selected_embedding_service_id is None and not has_id_map:
                raise ValueError(
                    "Embedding service selection required but not provided. "
                    "Please select an existing embedding service to use with this silo."
                )

        # Resolve embedding service
        embedding_service_id = None
        dependencies_created = []

        if export_data.silo.embedding_service_name:
            # Priority 1: Check ID map from full app import (already imported services)
            if embedding_service_id_map and export_data.silo.embedding_service_name in embedding_service_id_map:
                embedding_service_id = embedding_service_id_map[export_data.silo.embedding_service_name]
                logger.info(
                    f"Resolved embedding service via ID map: '{export_data.silo.embedding_service_name}' -> ID {embedding_service_id}"
                )
            # Priority 2: Use user-selected embedding service
            elif selected_embedding_service_id:
                embedding_service = (
                    self.session.query(EmbeddingService)
                    .filter(
                        EmbeddingService.service_id == selected_embedding_service_id,
                        EmbeddingService.app_id == app_id,
                    )
                    .first()
                )
                if not embedding_service:
                    raise ValueError(
                        f"Selected embedding service {selected_embedding_service_id} "
                        f"not found in app {app_id}"
                    )
                embedding_service_id = selected_embedding_service_id
                logger.info(
                    f"Using selected embedding service '{embedding_service.name}'"
                )
            # Priority 3: Try to resolve by name (for existing services)
            elif not export_data.embedding_service:
                existing_service = (
                    self.session.query(EmbeddingService)
                    .filter(
                        EmbeddingService.name == export_data.silo.embedding_service_name,
                        EmbeddingService.app_id == app_id,
                    )
                    .first()
                )
                if existing_service:
                    embedding_service_id = existing_service.service_id
                    logger.info(
                        f"Resolved embedding service by name: '{existing_service.name}'"
                    )
                else:
                    raise ValueError(
                        f"Embedding service '{export_data.silo.embedding_service_name}' "
                        f"not found. Please select an existing service."
                    )
            # Priority 4: Bundled - import it (last resort for individual silo imports)
            elif export_data.embedding_service:
                try:
                    embedding_import_summary = (
                        self.embedding_service_import.import_embedding_service(
                            export_data, app_id, ConflictMode.RENAME
                        )
                    )
                    embedding_service_id = embedding_import_summary.component_id
                    if embedding_import_summary.created:
                        dependencies_created.append(
                            f"Embedding Service: {embedding_import_summary.component_name}"
                        )
                    logger.info(
                        f"Imported bundled embedding service '{embedding_import_summary.component_name}'"
                    )
                except Exception as e:
                    logger.error(f"Failed to import bundled embedding service: {e}")
                    raise ValueError(
                        f"Failed to import bundled embedding service: {e}"
                    )
            else:
                raise ValueError(
                    f"Embedding service '{export_data.silo.embedding_service_name}' "
                    f"not found and not bundled. Please select an existing service."
                )

        # Resolve output parser (metadata definition)
        metadata_definition_id = None
        if export_data.silo.metadata_definition_name:
            # Priority 1: Check ID map from full app import (already imported parsers)
            if output_parser_id_map and export_data.silo.metadata_definition_name in output_parser_id_map:
                metadata_definition_id = output_parser_id_map[export_data.silo.metadata_definition_name]
                logger.info(
                    f"Resolved output parser via ID map: '{export_data.silo.metadata_definition_name}' -> ID {metadata_definition_id}"
                )
            # Priority 2: Try to resolve by name (for existing parsers)
            elif not export_data.output_parser:
                existing_parser = (
                    self.session.query(OutputParser)
                    .filter(
                        OutputParser.name == export_data.silo.metadata_definition_name,
                        OutputParser.app_id == app_id,
                    )
                    .first()
                )
                if existing_parser:
                    metadata_definition_id = existing_parser.parser_id
                    logger.info(
                        f"Resolved output parser by name: '{existing_parser.name}'"
                    )
                else:
                    logger.warning(
                        f"Output parser '{export_data.silo.metadata_definition_name}' "
                        f"not found. Silo will be created without metadata definition."
                    )
            # Priority 3: Bundled - import it (last resort for individual silo imports)
            elif export_data.output_parser:
                try:
                    parser_import_summary = (
                        self.output_parser_import.import_output_parser(
                            export_data, app_id, ConflictMode.RENAME
                        )
                    )
                    metadata_definition_id = parser_import_summary.component_id
                    if parser_import_summary.created:
                        dependencies_created.append(
                            f"Output Parser: {parser_import_summary.component_name}"
                        )
                    logger.info(
                        f"Imported bundled output parser '{parser_import_summary.component_name}'"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to import bundled output parser: {e}. "
                        f"Continuing without metadata definition."
                    )

        # Handle conflict
        final_name = export_data.silo.name
        existing_silo = self.get_by_name_and_app(final_name, app_id)

        if existing_silo:
            if conflict_mode == ConflictMode.FAIL:
                raise ValueError(
                    f"Silo '{final_name}' already exists in app {app_id}"
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
                        final_name = f"{export_data.silo.name} (imported {date_str} {counter})"
                        counter += 1
            elif conflict_mode == ConflictMode.OVERRIDE:
                # Update existing silo (CRITICAL: preserve vectors!)
                existing_silo.silo_type = export_data.silo.type
                existing_silo.vector_db_type = export_data.silo.vector_db_type
                existing_silo.embedding_service_id = embedding_service_id
                existing_silo.metadata_definition_id = metadata_definition_id
                existing_silo.fixed_metadata = export_data.silo.fixed_metadata
                existing_silo.description = export_data.silo.description
                # CRITICAL: Do NOT modify vector collection or vector data!

                self.session.add(existing_silo)
                self.session.commit()

                logger.info(
                    f"Overridden silo '{existing_silo.name}' - "
                    f"Vector data preserved"
                )

                return ImportSummarySchema(
                    component_type=ComponentType.SILO,
                    component_id=existing_silo.silo_id,
                    component_name=existing_silo.name,
                    mode=conflict_mode,
                    created=False,
                    dependencies_created=dependencies_created,
                    warnings=["Existing vector data preserved"],
                    next_steps=[],
                )

        # Create new silo (empty, no vectors)
        new_silo = Silo(
            app_id=app_id,
            name=final_name,
            silo_type=export_data.silo.type,  # Map type -> silo_type
            vector_db_type=export_data.silo.vector_db_type,
            embedding_service_id=embedding_service_id,
            metadata_definition_id=metadata_definition_id,
            fixed_metadata=export_data.silo.fixed_metadata,
            description=export_data.silo.description,
            status="active",  # Default status
        )

        self.session.add(new_silo)
        self.session.commit()
        self.session.refresh(new_silo)

        logger.info(
            f"Imported Silo '{final_name}' (ID: {new_silo.silo_id}) - "
            f"Empty silo created, no vectors"
        )

        return ImportSummarySchema(
            component_type=ComponentType.SILO,
            component_id=new_silo.silo_id,
            component_name=new_silo.name,
            mode=conflict_mode,
            created=True,
            dependencies_created=dependencies_created,
            warnings=[],
            next_steps=[
                "Upload documents to the silo to generate vector embeddings",
                "Configure embedding service API key if not already set",
            ],
        )
