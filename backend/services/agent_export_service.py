"""Service for exporting Agents with customizable dependencies."""

from typing import Optional, List
from sqlalchemy.orm import Session
from models.agent import Agent, AgentMCP, AgentTool
from schemas.export_schemas import (
    ExportAgentSchema,
    AgentExportFileSchema,
    ExportAgentToolRefSchema,
    ExportAgentMCPRefSchema,
)
from services.base_export_service import BaseExportService
from services.ai_service_export_service import AIServiceExportService
from services.silo_export_service import SiloExportService
from services.output_parser_export_service import OutputParserExportService
from services.mcp_config_export_service import MCPConfigExportService
from repositories.agent_repository import AgentRepository
import logging

logger = logging.getLogger(__name__)


class AgentExportService(BaseExportService):
    """Service for exporting Agents (configuration only, no conversations)."""

    def __init__(self, session: Session):
        """Initialize Agent export service.

        Args:
            session: SQLAlchemy database session
        """
        super().__init__(session)

    def export_agent(
        self,
        agent_id: int,
        app_id: int,
        user_id: Optional[int] = None,
        include_ai_service: bool = True,
        include_silo: bool = True,
        include_output_parser: bool = True,
        include_mcp_configs: bool = True,
        include_agent_tools: bool = True,
    ) -> AgentExportFileSchema:
        """Export Agent to JSON structure.

        Note: Exports agent CONFIGURATION only (no conversation history).
        Conversation history is NEVER exported to preserve privacy and
        reduce file size.

        Args:
            agent_id: ID of agent to export
            app_id: App ID (for permission check)
            user_id: User ID (for permission check, optional)
            include_ai_service: Bundle AI service in export
            include_silo: Bundle silo in export
            include_output_parser: Bundle output parser in export
            include_mcp_configs: Bundle MCP configs in export
            include_agent_tools: Bundle agent tools (other agents) in export

        Returns:
            AgentExportFileSchema: Export file structure

        Raises:
            ValueError: If agent not found or permission denied
        """
        # Load agent
        agent = AgentRepository.get_by_id(self.session, agent_id)
        if not agent:
            raise ValueError(f"Agent with ID {agent_id} not found")

        # Check if it's an OCR agent and reload with full OCR data if needed
        if agent.type == 'ocr_agent':
            agent = AgentRepository.get_ocr_agent_by_id(self.session, agent_id)
            if not agent:
                raise ValueError(f"OCR Agent with ID {agent_id} not found")

        # Permission check
        if agent.app_id != app_id:
            raise ValueError(
                f"Agent {agent_id} does not belong to app {app_id} "
                "(permission denied)"
            )

        # Get reference names
        service_name = None
        if agent.ai_service:
            service_name = agent.ai_service.name

        silo_name = None
        if agent.silo:
            silo_name = agent.silo.name

        output_parser_name = None
        if agent.output_parser:
            output_parser_name = agent.output_parser.name

        # OCR-specific fields
        vision_service_name = None
        vision_system_prompt = None
        text_system_prompt = None
        if hasattr(agent, 'vision_service_rel') and agent.vision_service_rel:
            vision_service_name = agent.vision_service_rel.name
        if hasattr(agent, 'vision_system_prompt'):
            vision_system_prompt = agent.vision_system_prompt
        if hasattr(agent, 'text_system_prompt'):
            text_system_prompt = agent.text_system_prompt

        # Get agent tool references
        agent_tool_refs = []
        tool_associations = AgentRepository.get_agent_tool_associations(
            self.session, agent_id
        )
        for assoc in tool_associations:
            if assoc.tool:
                agent_tool_refs.append(
                    ExportAgentToolRefSchema(tool_agent_name=assoc.tool.name)
                )

        # Get MCP references
        agent_mcp_refs = []
        mcp_associations = AgentRepository.get_agent_mcp_associations(
            self.session, agent_id
        )
        for assoc in mcp_associations:
            if assoc.mcp:
                agent_mcp_refs.append(
                    ExportAgentMCPRefSchema(mcp_name=assoc.mcp.name)
                )

        # Create export schema
        export_agent = ExportAgentSchema(
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            prompt_template=agent.prompt_template,
            service_name=service_name,
            silo_name=silo_name,
            output_parser_name=output_parser_name,
            agent_tool_refs=agent_tool_refs,
            agent_mcp_refs=agent_mcp_refs,
            has_memory=agent.has_memory,
            memory_max_messages=agent.memory_max_messages,
            memory_max_tokens=agent.memory_max_tokens,
            memory_summarize_threshold=agent.memory_summarize_threshold,
            temperature=agent.temperature,
            # OCR-specific fields
            vision_service_name=vision_service_name,
            vision_system_prompt=vision_system_prompt,
            text_system_prompt=text_system_prompt,
        )

        # Create metadata
        metadata = self.create_metadata(user_id, app_id)

        # Optionally bundle dependencies
        bundled_ai_service = None
        bundled_silo = None
        bundled_output_parser = None
        bundled_mcp_configs = []
        bundled_agent_tools = []

        # Bundle AI Service
        if include_ai_service and agent.service_id:
            try:
                ai_service_export = AIServiceExportService(self.session)
                ai_export_file = ai_service_export.export_ai_service(
                    agent.service_id, app_id, user_id
                )
                bundled_ai_service = ai_export_file.ai_service
            except Exception as e:
                logger.warning(
                    f"Failed to bundle AI service {agent.service_id}: {e}"
                )

        # Bundle Silo
        if include_silo and agent.silo_id:
            try:
                silo_export = SiloExportService(self.session)
                silo_export_file = silo_export.export_silo(
                    agent.silo_id, app_id, user_id, include_dependencies=True
                )
                bundled_silo = silo_export_file.silo
            except Exception as e:
                logger.warning(f"Failed to bundle silo {agent.silo_id}: {e}")

        # Bundle Output Parser
        if include_output_parser and agent.output_parser_id:
            try:
                parser_export = OutputParserExportService(self.session)
                parser_export_file = parser_export.export_output_parser(
                    agent.output_parser_id, app_id, user_id
                )
                bundled_output_parser = parser_export_file.output_parser
            except Exception as e:
                logger.warning(
                    f"Failed to bundle output parser "
                    f"{agent.output_parser_id}: {e}"
                )

        # Bundle MCP Configs
        if include_mcp_configs:
            for assoc in mcp_associations:
                if assoc.mcp:
                    try:
                        mcp_export = MCPConfigExportService(self.session)
                        mcp_export_file = mcp_export.export_mcp_config(
                            assoc.mcp.config_id, app_id, user_id
                        )
                        bundled_mcp_configs.append(mcp_export_file.mcp_config)
                    except Exception as e:
                        logger.warning(
                            f"Failed to bundle MCP config "
                            f"{assoc.mcp.config_id}: {e}"
                        )

        # Bundle Agent Tools (other agents)
        if include_agent_tools:
            for assoc in tool_associations:
                if assoc.tool:
                    try:
                        # Recursively export tool agent (without its own tools
                        # to avoid circular references)
                        tool_agent_export = self.export_agent(
                            assoc.tool.agent_id,
                            app_id,
                            user_id,
                            include_ai_service=True,
                            include_silo=False,
                            include_output_parser=True,
                            include_mcp_configs=False,
                            include_agent_tools=False,  # Prevent recursion
                        )
                        bundled_agent_tools.append(tool_agent_export.agent)
                    except Exception as e:
                        logger.warning(
                            f"Failed to bundle agent tool "
                            f"{assoc.tool.agent_id}: {e}"
                        )

        return AgentExportFileSchema(
            metadata=metadata,
            agent=export_agent,
            ai_service=bundled_ai_service,
            silo=bundled_silo,
            output_parser=bundled_output_parser,
            mcp_configs=bundled_mcp_configs,
            agent_tools=bundled_agent_tools,
        )
