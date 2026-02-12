"""Service for exporting complete app configuration."""

from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

from schemas.export_schemas import (
    AppExportFileSchema,
    ExportMetadataSchema,
    ExportAppSchema,
    ExportAIServiceSchema,
    ExportEmbeddingServiceSchema,
    ExportOutputParserSchema,
    ExportMCPConfigSchema,
    ExportSiloSchema,
    ExportAgentSchema,
)
from services.base_export_service import BaseExportService
from services.ai_service_export_service import AIServiceExportService
from services.embedding_service_export_service import EmbeddingServiceExportService
from services.output_parser_export_service import OutputParserExportService
from services.mcp_config_export_service import MCPConfigExportService
from services.silo_export_service import SiloExportService
from services.agent_export_service import AgentExportService
from repositories.app_repository import AppRepository
import logging

logger = logging.getLogger(__name__)


class FullAppExportService(BaseExportService):
    """Service for exporting complete app configuration.

    Orchestrates individual component export services to create a
    comprehensive app export including all AI services, embedding
    services, output parsers, MCP configs, silos, and agents.

    Excludes:
    - User accounts and permissions (security)
    - Conversation history (privacy, file size)
    - Silo vector data (heavy data)
    - File uploads and attachments (heavy data)
    - API keys and secrets (security - handled by component services)
    - Usage statistics (transient data)
    """

    def __init__(self, session: Session):
        """Initialize full app export service.

        Args:
            session: SQLAlchemy database session
        """
        super().__init__(session)
        self.app_repo = AppRepository(session)

        # Initialize component export services
        self.ai_service_export = AIServiceExportService(session)
        self.embedding_export = EmbeddingServiceExportService(session)
        self.parser_export = OutputParserExportService(session)
        self.mcp_export = MCPConfigExportService(session)
        self.silo_export = SiloExportService(session)
        self.agent_export = AgentExportService(session)

    def export_full_app(
        self, app_id: int, user_id: Optional[int] = None
    ) -> AppExportFileSchema:
        """Export complete app configuration to JSON structure.

        Args:
            app_id: ID of app to export
            user_id: User ID (for metadata, optional)

        Returns:
            AppExportFileSchema: Complete app export structure

        Raises:
            ValueError: If app not found
        """
        # Get app details
        app = self.app_repo.get_by_id(app_id)
        if not app:
            raise ValueError(f"App with ID {app_id} not found")

        logger.info(f"Starting full export for app '{app.name}' (ID: {app_id})")

        # Export all components in dependency order
        ai_services = self._export_all_ai_services(app_id)
        embedding_services = self._export_all_embedding_services(app_id)
        output_parsers = self._export_all_output_parsers(app_id)
        mcp_configs = self._export_all_mcp_configs(app_id)
        silos = self._export_all_silos(app_id)
        agents = self._export_all_agents(app_id)

        # Build app metadata
        app_schema = ExportAppSchema(
            name=app.name,
            agent_rate_limit=app.agent_rate_limit,
            enable_langsmith=bool(app.langsmith_api_key),
        )

        # Build export metadata
        metadata = self.create_metadata(user_id, app_id)

        # Construct full export file
        export_file = AppExportFileSchema(
            metadata=metadata,
            app=app_schema,
            ai_services=ai_services,
            embedding_services=embedding_services,
            output_parsers=output_parsers,
            mcp_configs=mcp_configs,
            silos=silos,
            repositories=[],  # Phase 6 not yet implemented
            agents=agents,
        )

        logger.info(
            f"Completed full export for app '{app.name}': "
            f"{len(ai_services)} AI services, "
            f"{len(embedding_services)} embedding services, "
            f"{len(output_parsers)} output parsers, "
            f"{len(mcp_configs)} MCP configs, "
            f"{len(silos)} silos, "
            f"{len(agents)} agents"
        )

        return export_file

    def _export_all_ai_services(self, app_id: int) -> List[ExportAIServiceSchema]:
        """Export all AI services for app.

        Args:
            app_id: App ID

        Returns:
            List of AI service export schemas
        """
        services = self.app_repo.get_ai_services_by_app_id(app_id)
        logger.info(f"Found {len(services)} AI services for app {app_id}")
        exported = []
        for service in services:
            try:
                export_file = self.ai_service_export.export_ai_service(
                    service.service_id, app_id
                )
                exported.append(export_file.ai_service)
            except Exception as e:
                logger.warning(
                    f"Failed to export AI service {service.service_id}: {e}",
                    exc_info=True
                )
        logger.info(f"Successfully exported {len(exported)}/{len(services)} AI services")
        return exported

    def _export_all_embedding_services(
        self, app_id: int
    ) -> List[ExportEmbeddingServiceSchema]:
        """Export all embedding services for app.

        Args:
            app_id: App ID

        Returns:
            List of embedding service export schemas
        """
        services = self.app_repo.get_embedding_services_by_app_id(app_id)
        logger.info(f"Found {len(services)} embedding services for app {app_id}")
        exported = []
        for service in services:
            try:
                export_file = self.embedding_export.export_embedding_service(
                    service.service_id, app_id
                )
                exported.append(export_file.embedding_service)
            except Exception as e:
                logger.warning(
                    f"Failed to export embedding service {service.service_id}: {e}",
                    exc_info=True
                )
        logger.info(f"Successfully exported {len(exported)}/{len(services)} embedding services")
        return exported

    def _export_all_output_parsers(
        self, app_id: int
    ) -> List[ExportOutputParserSchema]:
        """Export all output parsers for app.

        Args:
            app_id: App ID

        Returns:
            List of output parser export schemas
        """
        parsers = self.app_repo.get_output_parsers_by_app_id(app_id)
        logger.info(f"Found {len(parsers)} output parsers for app {app_id}")
        exported = []
        for parser in parsers:
            try:
                export_file = self.parser_export.export_output_parser(
                    parser.parser_id, app_id
                )
                exported.append(export_file.output_parser)
            except Exception as e:
                logger.warning(
                    f"Failed to export output parser {parser.parser_id}: {e}",
                    exc_info=True
                )
        logger.info(f"Successfully exported {len(exported)}/{len(parsers)} output parsers")
        return exported

    def _export_all_mcp_configs(self, app_id: int) -> List[ExportMCPConfigSchema]:
        """Export all MCP configs for app.

        Args:
            app_id: App ID

        Returns:
            List of MCP config export schemas
        """
        configs = self.app_repo.get_mcp_configs_by_app_id(app_id)
        logger.info(f"Found {len(configs)} MCP configs for app {app_id}")
        exported = []
        for config in configs:
            try:
                export_file = self.mcp_export.export_mcp_config(
                    config.config_id, app_id
                )
                exported.append(export_file.mcp_config)
            except Exception as e:
                logger.warning(
                    f"Failed to export MCP config {config.config_id}: {e}",
                    exc_info=True
                )
        logger.info(f"Successfully exported {len(exported)}/{len(configs)} MCP configs")
        return exported

    def _export_all_silos(self, app_id: int) -> List[ExportSiloSchema]:
        """Export all silos for app.

        Args:
            app_id: App ID

        Returns:
            List of silo export schemas
        """
        silos = self.app_repo.get_silos_by_app_id(app_id)
        logger.info(f"Found {len(silos)} silos for app {app_id}")
        exported = []
        for silo in silos:
            try:
                export_file = self.silo_export.export_silo(silo.silo_id, app_id)
                exported.append(export_file.silo)
            except Exception as e:
                logger.warning(
                    f"Failed to export silo {silo.silo_id}: {e}",
                    exc_info=True
                )
        logger.info(f"Successfully exported {len(exported)}/{len(silos)} silos")
        return exported

    def _export_all_agents(self, app_id: int) -> List[ExportAgentSchema]:
        """Export all agents for app with all dependencies bundled.

        Args:
            app_id: App ID

        Returns:
            List of agent export schemas
        """
        agents = self.app_repo.get_agents_by_app_id(app_id)
        logger.info(f"Found {len(agents)} agents for app {app_id}")
        
        # Filter out agents without AI service (data inconsistency)
        valid_agents = [a for a in agents if a.service_id is not None]
        if len(valid_agents) < len(agents):
            skipped = len(agents) - len(valid_agents)
            logger.warning(
                f"Skipping {skipped} agent(s) without AI service (data inconsistency)"
            )
        
        exported = []
        for agent in valid_agents:
            try:
                # Export agent with all dependencies enabled
                export_file = self.agent_export.export_agent(
                    agent.agent_id,
                    app_id,
                    include_ai_service=True,
                    include_silo=True,
                    include_output_parser=True,
                    include_mcp_configs=True,
                    include_agent_tools=True,
                )
                exported.append(export_file.agent)
            except Exception as e:
                logger.warning(
                    f"Failed to export agent {agent.agent_id}: {e}",
                    exc_info=True
                )
        logger.info(f"Successfully exported {len(exported)}/{len(valid_agents)} agents")
        return exported
