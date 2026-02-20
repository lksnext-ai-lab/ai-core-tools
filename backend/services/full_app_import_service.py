"""Service for importing complete app configuration."""

import time
from typing import Optional, List, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from schemas.export_schemas import AppExportFileSchema
from schemas.import_schemas import (
    ConflictMode,
    FullAppImportSummarySchema,
)
from services.ai_service_import_service import AIServiceImportService
from services.embedding_service_import_service import (
    EmbeddingServiceImportService,
)
from services.output_parser_import_service import OutputParserImportService
from services.mcp_config_import_service import MCPConfigImportService
from services.silo_import_service import SiloImportService
from services.repository_import_service import RepositoryImportService
from services.domain_import_service import DomainImportService
from services.agent_import_service import AgentImportService
from repositories.app_repository import AppRepository
from models.app import App
import logging

logger = logging.getLogger(__name__)


class FullAppImportService:
    """Service for importing complete app configuration.

    Orchestrates individual component import services to import
    a full app configuration with dependency-aware ordering.
    """

    # Import order (respects dependencies)
    IMPORT_ORDER = [
        "ai_services",
        "embedding_services",
        "output_parsers",
        "mcp_configs",
        "silos",
        "repositories",
        "domains",
        "agents",
    ]

    def __init__(self, session: Session):
        """Initialize full app import service.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.app_repo = AppRepository(session)

        # Initialize component import services
        self.ai_service_import = AIServiceImportService(session)
        self.embedding_import = EmbeddingServiceImportService(session)
        self.parser_import = OutputParserImportService(session)
        self.mcp_import = MCPConfigImportService(session)
        self.silo_import = SiloImportService(session)
        self.repository_import = RepositoryImportService(session)
        self.domain_import = DomainImportService(session)
        self.agent_import = AgentImportService(session)
        
        # Track name mappings for renamed components (original_name -> new_id)
        self.ai_service_mapping = {}
        self.embedding_service_mapping = {}
        self.parser_mapping = {}

    def import_full_app(
        self,
        export_data: AppExportFileSchema,
        user_id: int,
        conflict_mode: ConflictMode = ConflictMode.FAIL,
        new_name: Optional[str] = None,
    ) -> FullAppImportSummarySchema:
        """Import complete app configuration (always creates NEW app).

        Args:
            export_data: Parsed export file
            user_id: User ID creating the app
            conflict_mode: How to handle name conflicts (fail/rename/override)
            new_name: Optional custom name for the imported app

        Returns:
            FullAppImportSummarySchema: Comprehensive import summary

        Raises:
            ValueError: If validation fails or app name conflict
        """
        start_time = time.time()

        # Create new app
        app_id, app_name = self._create_new_app(
            export_data, user_id, conflict_mode, new_name
        )

        logger.info(
            f"Starting full app import into app '{app_name}' (ID: {app_id})"
        )

        components_imported = {}
        components_skipped = {}
        all_warnings = []
        all_errors = []
        
        # Track component name -> new ID mappings for dependency resolution
        component_id_mappings = {
            "ai_services": {},  # name -> new service_id
            "embedding_services": {},  # name -> new service_id
            "output_parsers": {},  # name -> new parser_id
            "silos": {},  # name -> new silo_id
        }

        # Import ALL components in dependency order (wrapped in try-except for rollback)
        try:
            for component_type in self.IMPORT_ORDER:
                component_data = getattr(export_data, component_type, [])
                logger.info(f"Starting import of {len(component_data)} {component_type}")
                try:
                    count, warnings, mappings = self._import_component_type(
                        component_type, export_data, app_id, conflict_mode, component_id_mappings
                    )
                    components_imported[component_type] = count
                    all_warnings.extend(warnings)
                    # Update mappings for dependency resolution
                    if component_type in component_id_mappings:
                        component_id_mappings[component_type].update(mappings)
                    logger.info(f"Successfully imported {count}/{len(component_data)} {component_type}")
                except Exception as e:
                    error_msg = f"{component_type}: {str(e)}"
                    all_errors.append(error_msg)
                    logger.error(f"Failed to import {component_type}: {e}", exc_info=True)
                    # Skip remaining components of this type
                    components_skipped[component_type] = len(component_data)

            # Commit transaction if no errors
            if not all_errors:
                self.session.commit()
                logger.info(
                    f"Successfully committed full app import for '{app_name}'"
                )
            else:
                self.session.rollback()
                logger.error(
                    f"Rolling back full app import due to errors: {all_errors}"
                )

        except Exception as e:
            self.session.rollback()
            logger.error(f"Full app import failed with exception: {e}")
            raise

        duration = time.time() - start_time

        return FullAppImportSummarySchema(
            app_name=app_name,
            app_id=app_id,
            total_components=sum(components_imported.values()),
            components_imported=components_imported,
            components_skipped=components_skipped,
            total_warnings=all_warnings,
            total_errors=all_errors,
            duration_seconds=round(duration, 2),
        )

    def _get_app_name(self, app_id: int) -> str:
        """Get app name by ID.

        Args:
            app_id: App ID

        Returns:
            App name

        Raises:
            ValueError: If app not found
        """
        app = self.app_repo.get_by_id(app_id)
        if not app:
            raise ValueError(f"App with ID {app_id} not found")
        return app.name

    def _create_new_app(
        self,
        export_data: AppExportFileSchema,
        user_id: int,
        conflict_mode: ConflictMode = ConflictMode.FAIL,
        new_name: Optional[str] = None,
    ) -> Tuple[int, str]:
        """Create new app from export metadata.

        Args:
            export_data: Export file data
            user_id: User ID creating the app
            conflict_mode: How to handle name conflicts
            new_name: Optional custom name for the app

        Returns:
            Tuple of (new_app_id, app_name)
            
        Raises:
            ValueError: If app name conflict and mode is FAIL
        """
        base_name = export_data.app.name
        final_name = new_name if new_name else base_name

        # Check for name conflict
        existing_app = (
            self.session.query(App).filter(App.name == final_name).first()
        )
        
        if existing_app:
            if conflict_mode == ConflictMode.FAIL:
                raise ValueError(f"App '{final_name}' already exists")
            elif conflict_mode == ConflictMode.RENAME:
                # Auto-generate unique name with timestamp
                if not new_name:
                    timestamp = datetime.now().strftime("%Y-%m-%d")
                    final_name = f"{base_name} (imported {timestamp})"
                    counter = 1
                    while self.session.query(App).filter(App.name == final_name).first():
                        final_name = f"{base_name} (imported {timestamp} {counter})"
                        counter += 1
            elif conflict_mode == ConflictMode.OVERRIDE:
                # For OVERRIDE mode in full app, we still create a NEW app
                # but overwrite the existing one's configuration
                # This is handled differently than components
                raise ValueError(
                    "OVERRIDE mode not supported for full app import. "
                    "Use RENAME mode to create a new app with auto-generated name."
                )

        # Create new app
        new_app = App(
            name=final_name,
            owner_id=user_id,
            create_date=datetime.now(),
            # Copy additional metadata from export
            agent_rate_limit=export_data.app.agent_rate_limit,
        )
        self.session.add(new_app)
        self.session.flush()  # Get app_id without committing

        logger.info(f"Created new app '{final_name}' (ID: {new_app.app_id})")

        return new_app.app_id, final_name

    def _import_component_type(
        self,
        component_type: str,
        export_data: AppExportFileSchema,
        app_id: int,
        conflict_mode: ConflictMode,
        component_id_mappings: dict,
    ) -> Tuple[int, List[str], dict]:
        """Import all components of a specific type.

        Args:
            component_type: Type of component to import
            export_data: Export file data
            app_id: Target app ID
            conflict_mode: Conflict resolution mode
            component_id_mappings: Existing name->ID mappings for dependency resolution

        Returns:
            Tuple of (count_imported, warnings, new_mappings)
        """
        component_data = getattr(export_data, component_type, [])
        if not component_data:
            return 0, [], {}

        warnings = []
        count = 0
        new_mappings = {}

        # Route to appropriate import service
        if component_type == "ai_services":
            for item in component_data:
                # Build individual export file schema
                from schemas.export_schemas import AIServiceExportFileSchema

                item_export = AIServiceExportFileSchema(
                    metadata=export_data.metadata, ai_service=item
                )
                original_name = item.name  # Store original name from export
                logger.debug(f"Importing AI service: {original_name}")
                result = self.ai_service_import.import_ai_service(
                    export_data=item_export,
                    app_id=app_id,
                    conflict_mode=conflict_mode,
                )
                warnings.extend(result.warnings)
                # Track mapping: original name -> new ID
                new_mappings[original_name] = result.component_id
                logger.debug(f"Mapped AI service '{original_name}' -> ID {result.component_id}")
                count += 1

        elif component_type == "embedding_services":
            for item in component_data:
                from schemas.export_schemas import (
                    EmbeddingServiceExportFileSchema,
                )

                item_export = EmbeddingServiceExportFileSchema(
                    metadata=export_data.metadata, embedding_service=item
                )
                original_name = item.name  # Store original name from export
                logger.debug(f"Importing embedding service: {original_name}")
                result = self.embedding_import.import_embedding_service(
                    export_data=item_export,
                    app_id=app_id,
                    conflict_mode=conflict_mode,
                )
                warnings.extend(result.warnings)
                # Track mapping: original name -> new ID
                new_mappings[original_name] = result.component_id
                logger.debug(f"Mapped embedding service '{original_name}' -> ID {result.component_id}")
                count += 1

        elif component_type == "output_parsers":
            for item in component_data:
                from schemas.export_schemas import OutputParserExportFileSchema

                item_export = OutputParserExportFileSchema(
                    metadata=export_data.metadata, output_parser=item
                )
                original_name = item.name  # Store original name from export
                logger.debug(f"Importing output parser: {original_name}")
                result = self.parser_import.import_output_parser(
                    export_data=item_export,
                    app_id=app_id,
                    conflict_mode=conflict_mode,
                )
                warnings.extend(result.warnings)
                # Track mapping: original name -> new ID
                new_mappings[original_name] = result.component_id
                logger.debug(f"Mapped output parser '{original_name}' -> ID {result.component_id}")
                count += 1

        elif component_type == "mcp_configs":
            for item in component_data:
                from schemas.export_schemas import MCPConfigExportFileSchema

                item_export = MCPConfigExportFileSchema(
                    metadata=export_data.metadata, mcp_config=item
                )
                logger.debug(f"Importing MCP config: {item.name}")
                result = self.mcp_import.import_mcp_config(
                    export_data=item_export,
                    app_id=app_id,
                    conflict_mode=conflict_mode,
                )
                warnings.extend(result.warnings)
                count += 1

        elif component_type == "silos":
            for item in component_data:
                from schemas.export_schemas import SiloExportFileSchema

                item_export = SiloExportFileSchema(
                    metadata=export_data.metadata, silo=item
                )
                original_name = item.name
                logger.debug(f"Importing silo: {original_name}")
                result = self.silo_import.import_silo(
                    export_data=item_export,
                    app_id=app_id,
                    conflict_mode=conflict_mode,
                    embedding_service_id_map=component_id_mappings["embedding_services"],
                    output_parser_id_map=component_id_mappings["output_parsers"],
                )
                warnings.extend(result.warnings)
                # Track silo name -> ID for repos/domains
                new_mappings[original_name] = result.component_id
                logger.debug(
                    f"Mapped silo '{original_name}' "
                    f"-> ID {result.component_id}"
                )
                count += 1

        elif component_type == "repositories":
            for item in component_data:
                from schemas.export_schemas import (
                    RepositoryExportFileSchema,
                )

                item_export = RepositoryExportFileSchema(
                    metadata=export_data.metadata,
                    repository=item,
                )
                logger.debug(
                    f"Importing repository: {item.name}"
                )
                result = self.repository_import.import_repository(
                    export_data=item_export,
                    app_id=app_id,
                    conflict_mode=conflict_mode,
                    silo_id_map=component_id_mappings.get(
                        "silos", {}
                    ),
                    embedding_service_id_map=component_id_mappings[
                        "embedding_services"
                    ],
                    output_parser_id_map=component_id_mappings[
                        "output_parsers"
                    ],
                )
                warnings.extend(result.warnings)
                count += 1

        elif component_type == "domains":
            for item in component_data:
                from schemas.export_schemas import (
                    DomainExportFileSchema,
                )

                item_export = DomainExportFileSchema(
                    metadata=export_data.metadata,
                    domain=item,
                )
                logger.debug(
                    f"Importing domain: {item.name}"
                )
                result = self.domain_import.import_domain(
                    export_data=item_export,
                    app_id=app_id,
                    conflict_mode=conflict_mode,
                    silo_id_map=component_id_mappings.get(
                        "silos", {}
                    ),
                    embedding_service_id_map=component_id_mappings[
                        "embedding_services"
                    ],
                    output_parser_id_map=component_id_mappings[
                        "output_parsers"
                    ],
                )
                warnings.extend(result.warnings)
                count += 1

        elif component_type == "agents":
            for item in component_data:
                from schemas.export_schemas import AgentExportFileSchema

                item_export = AgentExportFileSchema(
                    metadata=export_data.metadata, agent=item
                )
                logger.debug(f"Importing agent: {item.name}")
                try:
                    result = self.agent_import.import_agent(
                        export_data=item_export,
                        app_id=app_id,
                        conflict_mode=conflict_mode,
                        ai_service_id_map=component_id_mappings["ai_services"],
                    )
                    warnings.extend(result.warnings)
                    count += 1
                except Exception as e:
                    # Log error but continue with next agent (allows partial import)
                    logger.warning(
                        f"Failed to import agent '{item.name}': {e}", 
                        exc_info=True
                    )
                    warnings.append(f"Agent '{item.name}' import failed: {str(e)}")

        return count, warnings, new_mappings
