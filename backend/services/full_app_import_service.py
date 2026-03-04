"""Service for importing complete app configuration."""

import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from schemas.export_schemas import AppExportFileSchema
from schemas.import_schemas import (
    ConflictMode,
    FullAppImportSummarySchema,
    ComponentPreviewItem,
    DependencyInfo,
    AppImportPreviewSchema,
    ComponentType,
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

    def preview_import(
        self,
        export_data: AppExportFileSchema,
    ) -> AppImportPreviewSchema:
        """Preview full app import without importing.

        Iterates all component types, checks for conflicts against
        existing apps, builds dependency edges, and returns a
        structured preview. Read-only -- no DB mutations.

        Args:
            export_data: Parsed export file

        Returns:
            AppImportPreviewSchema: Full preview of what will happen
        """
        from core.export_constants import validate_export_version
        from models.app import App

        validate_export_version(
            export_data.metadata.export_version
        )

        global_warnings = []
        dependencies = []

        # Check app name conflict
        existing_app = (
            self.session.query(App)
            .filter(App.name == export_data.app.name)
            .first()
        )
        if existing_app:
            global_warnings.append(
                f"App '{export_data.app.name}' already exists. "
                f"Use rename mode to auto-generate a new name."
            )

        # Component counts
        component_counts = {
            "ai_services": len(export_data.ai_services),
            "embedding_services": len(
                export_data.embedding_services
            ),
            "output_parsers": len(export_data.output_parsers),
            "mcp_configs": len(export_data.mcp_configs),
            "silos": len(export_data.silos),
            "repositories": len(export_data.repositories),
            "domains": len(export_data.domains),
            "agents": len(export_data.agents),
        }

        # Preview AI services
        ai_service_previews = []
        for svc in export_data.ai_services:
            ai_service_previews.append(ComponentPreviewItem(
                component_type=ComponentType.AI_SERVICE,
                component_name=svc.name,
                bundled=True,
                needs_api_key=True,
                provider=svc.provider,
            ))

        # Preview embedding services
        embedding_previews = []
        for svc in export_data.embedding_services:
            embedding_previews.append(ComponentPreviewItem(
                component_type=ComponentType.EMBEDDING_SERVICE,
                component_name=svc.name,
                bundled=True,
                needs_api_key=True,
                provider=svc.provider,
            ))

        # Preview output parsers
        parser_previews = []
        for p in export_data.output_parsers:
            parser_previews.append(ComponentPreviewItem(
                component_type=ComponentType.OUTPUT_PARSER,
                component_name=p.name,
                bundled=True,
            ))

        # Preview MCP configs
        mcp_previews = []
        for m in export_data.mcp_configs:
            mcp_previews.append(ComponentPreviewItem(
                component_type=ComponentType.MCP_CONFIG,
                component_name=m.name,
                bundled=True,
            ))

        # Preview silos + dependency edges
        silo_previews = []
        for s in export_data.silos:
            silo_previews.append(ComponentPreviewItem(
                component_type=ComponentType.SILO,
                component_name=s.name,
                bundled=True,
            ))
            if s.embedding_service_name:
                dependencies.append(DependencyInfo(
                    source_type="silo",
                    source_name=s.name,
                    depends_on_type="embedding_service",
                    depends_on_name=s.embedding_service_name,
                    mandatory=True,
                    bundled=any(
                        e.name == s.embedding_service_name
                        for e in export_data.embedding_services
                    ),
                ))
            if s.metadata_definition_name:
                dependencies.append(DependencyInfo(
                    source_type="silo",
                    source_name=s.name,
                    depends_on_type="output_parser",
                    depends_on_name=s.metadata_definition_name,
                    mandatory=False,
                    bundled=any(
                        p.name == s.metadata_definition_name
                        for p in export_data.output_parsers
                    ),
                ))

        # Preview repositories + dependency edges
        repo_previews = []
        for r in export_data.repositories:
            repo_previews.append(ComponentPreviewItem(
                component_type=ComponentType.REPOSITORY,
                component_name=r.name,
                bundled=True,
            ))
            if r.silo_name:
                dependencies.append(DependencyInfo(
                    source_type="repository",
                    source_name=r.name,
                    depends_on_type="silo",
                    depends_on_name=r.silo_name,
                    mandatory=False,
                    bundled=any(
                        s.name == r.silo_name
                        for s in export_data.silos
                    ),
                ))

        # Preview domains + dependency edges
        domain_previews = []
        for d in export_data.domains:
            domain_previews.append(ComponentPreviewItem(
                component_type=ComponentType.DOMAIN,
                component_name=d.name,
                bundled=True,
            ))
            if d.silo_name:
                dependencies.append(DependencyInfo(
                    source_type="domain",
                    source_name=d.name,
                    depends_on_type="silo",
                    depends_on_name=d.silo_name,
                    mandatory=False,
                    bundled=any(
                        s.name == d.silo_name
                        for s in export_data.silos
                    ),
                ))

        # Preview agents + dependency edges
        agent_previews = []
        for a in export_data.agents:
            agent_previews.append(ComponentPreviewItem(
                component_type=ComponentType.AGENT,
                component_name=a.name,
                bundled=True,
            ))
            if a.service_name:
                dependencies.append(DependencyInfo(
                    source_type="agent",
                    source_name=a.name,
                    depends_on_type="ai_service",
                    depends_on_name=a.service_name,
                    mandatory=True,
                    bundled=any(
                        s.name == a.service_name
                        for s in export_data.ai_services
                    ),
                ))
            if a.silo_name:
                dependencies.append(DependencyInfo(
                    source_type="agent",
                    source_name=a.name,
                    depends_on_type="silo",
                    depends_on_name=a.silo_name,
                    mandatory=False,
                    bundled=any(
                        s.name == a.silo_name
                        for s in export_data.silos
                    ),
                ))
            if a.output_parser_name:
                dependencies.append(DependencyInfo(
                    source_type="agent",
                    source_name=a.name,
                    depends_on_type="output_parser",
                    depends_on_name=a.output_parser_name,
                    mandatory=False,
                    bundled=any(
                        p.name == a.output_parser_name
                        for p in export_data.output_parsers
                    ),
                ))
            for mcp_ref in a.agent_mcp_refs:
                dependencies.append(DependencyInfo(
                    source_type="agent",
                    source_name=a.name,
                    depends_on_type="mcp_config",
                    depends_on_name=mcp_ref.mcp_name,
                    mandatory=False,
                    bundled=any(
                        m.name == mcp_ref.mcp_name
                        for m in export_data.mcp_configs
                    ),
                ))
            for tool_ref in a.agent_tool_refs:
                dependencies.append(DependencyInfo(
                    source_type="agent",
                    source_name=a.name,
                    depends_on_type="agent",
                    depends_on_name=tool_ref.tool_agent_name,
                    mandatory=False,
                    bundled=any(
                        ag.name == tool_ref.tool_agent_name
                        for ag in export_data.agents
                    ),
                ))

        return AppImportPreviewSchema(
            valid=True,
            export_version=(
                export_data.metadata.export_version
            ),
            app_name=export_data.app.name,
            ai_services=ai_service_previews,
            embedding_services=embedding_previews,
            output_parsers=parser_previews,
            mcp_configs=mcp_previews,
            silos=silo_previews,
            repositories=repo_previews,
            domains=domain_previews,
            agents=agent_previews,
            dependencies=dependencies,
            component_counts=component_counts,
            global_warnings=global_warnings,
        )

    def import_full_app(
        self,
        export_data: AppExportFileSchema,
        user_id: int,
        conflict_mode: ConflictMode = ConflictMode.FAIL,
        new_name: Optional[str] = None,
        component_selection: Optional[Dict[str, List[str]]] = None,
        api_keys: Optional[Dict[str, str]] = None,
    ) -> FullAppImportSummarySchema:
        """Import complete app configuration (always creates NEW app).

        Args:
            export_data: Parsed export file
            user_id: User ID creating the app
            conflict_mode: How to handle name conflicts (fail/rename/override)
            new_name: Optional custom name for the imported app
            component_selection: Optional dict mapping singular type names to
                lists of component names to import. If omitted, all components
                are imported.  Keys: ``ai_service``, ``embedding_service``,
                ``output_parser``, ``mcp_config``, ``silo``, ``repository``,
                ``domain``, ``agent``.
            api_keys: Optional dict mapping original service names to API keys
                to set on newly created AI/embedding services.

        Returns:
            FullAppImportSummarySchema: Comprehensive import summary

        Raises:
            ValueError: If validation fails or app name conflict
        """
        start_time = time.time()

        # Filter export_data based on component_selection
        if component_selection is not None:
            _TYPE_TO_FIELD: Dict[str, str] = {
                "ai_service": "ai_services",
                "embedding_service": "embedding_services",
                "output_parser": "output_parsers",
                "mcp_config": "mcp_configs",
                "silo": "silos",
                "repository": "repositories",
                "domain": "domains",
                "agent": "agents",
            }
            filtered: Dict[str, list] = {}
            for sel_type, field_name in _TYPE_TO_FIELD.items():
                selected_names = component_selection.get(sel_type)
                if selected_names is not None:
                    # User explicitly selected a subset of this type
                    selected_set = set(selected_names)
                    current = getattr(export_data, field_name, [])
                    filtered[field_name] = [
                        item for item in current
                        if item.name in selected_set
                    ]
                else:
                    # Type absent from selection = user deselected
                    # all items of this type
                    filtered[field_name] = []
            if filtered:
                export_data = export_data.model_copy(
                    update=filtered
                )
                logger.info(
                    "Component selection applied: "
                    + ", ".join(
                        f"{k}={len(v)}" for k, v in filtered.items()
                    )
                )

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
                        component_type, export_data, app_id, conflict_mode,
                        component_id_mappings, api_keys=api_keys,
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
                    # Rollback to clear any poisoned transaction state so that
                    # subsequent component types can still use the session
                    try:
                        self.session.rollback()
                    except Exception:
                        pass
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
        api_keys: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, List[str], dict]:
        """Import all components of a specific type.

        Args:
            component_type: Type of component to import
            export_data: Export file data
            app_id: Target app ID
            conflict_mode: Conflict resolution mode
            component_id_mappings: Existing name->ID mappings for
                dependency resolution
            api_keys: Optional dict of original service name -> API key
                to apply after creation.

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
                logger.debug(
                    f"Mapped AI service '{original_name}'"
                    f" -> ID {result.component_id}"
                )
                # Apply user-supplied API key if provided (no commit here;
                # the outer commit at the end of import_full_app persists it)
                if (
                    api_keys
                    and original_name in api_keys
                    and api_keys[original_name]
                ):
                    from models.ai_service import AIService as _AIService
                    svc_obj = self.session.get(
                        _AIService, result.component_id
                    )
                    if svc_obj:
                        svc_obj.api_key = api_keys[original_name]
                        logger.debug(
                            f"Applied API key for AI service"
                            f" '{original_name}'"
                        )
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
                logger.debug(
                    f"Mapped embedding service '{original_name}'"
                    f" -> ID {result.component_id}"
                )
                # Apply user-supplied API key if provided (no commit here;
                # the outer commit at the end of import_full_app persists it)
                if (
                    api_keys
                    and original_name in api_keys
                    and api_keys[original_name]
                ):
                    from models.embedding_service import (
                        EmbeddingService as _EmbeddingService,
                    )
                    emb_obj = self.session.get(
                        _EmbeddingService, result.component_id
                    )
                    if emb_obj:
                        emb_obj.api_key = api_keys[original_name]
                        logger.debug(
                            f"Applied API key for embedding service"
                            f" '{original_name}'"
                        )
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
