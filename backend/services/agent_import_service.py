"""Service for importing Agents with dependency selection."""

from typing import Optional, List, Dict
from datetime import datetime
from sqlalchemy.orm import Session
from models.agent import Agent, AgentMCP, AgentTool
from models.ai_service import AIService
from models.silo import Silo
from models.output_parser import OutputParser
from models.mcp_config import MCPConfig
from schemas.export_schemas import AgentExportFileSchema
from schemas.import_schemas import (
    ConflictMode,
    ValidateImportResponseSchema,
    ImportSummarySchema,
    ComponentType,
)
from core.export_constants import validate_export_version
from services.ai_service_import_service import AIServiceImportService
from services.silo_import_service import SiloImportService
from services.output_parser_import_service import OutputParserImportService
from services.mcp_config_import_service import MCPConfigImportService
from repositories.agent_repository import AgentRepository
from repositories.ai_service_repository import AIServiceRepository
from repositories.silo_repository import SiloRepository
from repositories.output_parser_repository import OutputParserRepository
from repositories.mcp_config_repository import MCPConfigRepository
import logging

logger = logging.getLogger(__name__)


class AgentImportService:
    """Service for importing Agents (configuration only)."""

    def __init__(self, session: Session):
        """Initialize Agent import service.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

        # Import services for bundled dependencies
        self.ai_service_import = AIServiceImportService(session)
        self.silo_import = SiloImportService(session)
        self.parser_import = OutputParserImportService(session)
        self.mcp_import = MCPConfigImportService(session)

    def get_by_name_and_app(
        self, name: str, app_id: int
    ) -> Optional[Agent]:
        """Get Agent by name and app ID.

        Args:
            name: Agent name
            app_id: App ID

        Returns:
            Optional[Agent]: Agent if found, None otherwise
        """
        return (
            self.session.query(Agent)
            .filter(Agent.name == name, Agent.app_id == app_id)
            .first()
        )

    def validate_import(
        self, export_data: AgentExportFileSchema, app_id: int
    ) -> ValidateImportResponseSchema:
        """Validate Agent import without importing.

        Args:
            export_data: Parsed export file
            app_id: Target app ID

        Returns:
            ValidateImportResponseSchema: Validation result
        """
        # Validate version
        validate_export_version(export_data.metadata.export_version)

        # Check for name conflict
        existing_agent = self.get_by_name_and_app(
            export_data.agent.name, app_id
        )

        warnings = []
        missing_dependencies = []
        requires_ai_service_selection = False

        # Check AI service dependency (MANDATORY)
        if export_data.agent.service_name:
            # If AI service is NOT bundled, require user selection
            if export_data.ai_service is None:
                requires_ai_service_selection = True
                warnings.append(
                    f"AI service '{export_data.agent.service_name}' not "
                    f"bundled. You must select an existing AI service."
                )
            else:
                #Bundled - validate it can be imported
                try:
                    from schemas.export_schemas import AIServiceExportFileSchema
                    
                    ai_service_export = AIServiceExportFileSchema(
                        metadata=export_data.metadata,
                        ai_service=export_data.ai_service
                    )
                    self.ai_service_import.validate_import(
                        ai_service_export, app_id
                    )
                except Exception as e:
                    warnings.append(
                        f"Bundled AI service validation issue: {e}"
                    )

        # Check optional dependencies
        if export_data.agent.silo_name and export_data.silo is None:
            existing_silo = (
                self.session.query(Silo)
                .filter(
                    Silo.name == export_data.agent.silo_name,
                    Silo.app_id == app_id,
                )
                .first()
            )
            if not existing_silo:
                warnings.append(
                    f"Silo '{export_data.agent.silo_name}' not found. "
                    f"Agent will be created without silo."
                )

        if (
            export_data.agent.output_parser_name
            and export_data.output_parser is None
        ):
            existing_parser = (
                self.session.query(OutputParser)
                .filter(
                    OutputParser.name == export_data.agent.output_parser_name,
                    OutputParser.app_id == app_id,
                )
                .first()
            )
            if not existing_parser:
                warnings.append(
                    f"Output parser "
                    f"'{export_data.agent.output_parser_name}' not found. "
                    f"Agent will be created without output parser."
                )

        return ValidateImportResponseSchema(
            component_type=ComponentType.AGENT,
            component_name=export_data.agent.name,
            has_conflict=existing_agent is not None,
            warnings=warnings,
            missing_dependencies=missing_dependencies,
            requires_ai_service_selection=requires_ai_service_selection,
        )

    def import_agent(
        self,
        export_data: AgentExportFileSchema,
        app_id: int,
        conflict_mode: ConflictMode = ConflictMode.FAIL,
        new_name: Optional[str] = None,
        selected_ai_service_id: Optional[int] = None,
        selected_silo_id: Optional[int] = None,
        selected_output_parser_id: Optional[int] = None,
    ) -> ImportSummarySchema:
        """Import Agent configuration.

        Important: Conversation history is NOT imported.

        Dependencies:
        - AI service (mandatory): Must be bundled or selected
        - Silo (optional): Bundled, existing, or selected
        - Output parser (optional): Bundled, existing, or selected
        - MCP configs (optional): Bundled or matched by name
        - Agent tools (optional): Bundled or matched by name

        Args:
            export_data: Parsed export file
            app_id: Target app ID
            conflict_mode: How to handle name conflicts
            new_name: New name if renaming
            selected_ai_service_id: User-selected AI service ID (if not
                bundled)
            selected_silo_id: User-selected silo ID (optional)
            selected_output_parser_id: User-selected parser ID (optional)

        Returns:
            ImportSummarySchema: Import result

        Raises:
            ValueError: If validation fails or mandatory dependencies missing
        """
        warnings = []

        # Validate version
        validate_export_version(export_data.metadata.export_version)

        # Step 0: Determine agent's final name (needed for dependency naming)
        agent_name = export_data.agent.name
        existing_agent = self.get_by_name_and_app(agent_name, app_id)

        if existing_agent:
            if conflict_mode == ConflictMode.FAIL:
                raise ValueError(f"Agent '{agent_name}' already exists")
            elif conflict_mode == ConflictMode.RENAME:
                if new_name:
                    agent_name = new_name
                else:
                    # Auto-generate unique name
                    base_name = agent_name
                    counter = 1
                    while self.get_by_name_and_app(agent_name, app_id):
                        agent_name = f"{base_name} ({counter})"
                        counter += 1
            # For OVERRIDE mode, keep original name
        elif new_name:
            # No conflict but user provided a custom name
            agent_name = new_name

        # Step 1: Import or resolve AI service (MANDATORY)
        service_id = None
        if export_data.ai_service:
            # Bundled AI service - import it
            try:
                from schemas.export_schemas import AIServiceExportFileSchema
                
                ai_service_export = AIServiceExportFileSchema(
                    metadata=export_data.metadata,
                    ai_service=export_data.ai_service
                )
                # Use custom name: {original_name} {agent_name}
                ai_service_custom_name = f"{export_data.ai_service.name} {agent_name}"
                ai_import_result = self.ai_service_import.import_ai_service(
                    ai_service_export,
                    app_id,
                    conflict_mode=ConflictMode.RENAME,
                    new_name=ai_service_custom_name,
                )
                # Find the imported service by name
                imported_service = (
                    self.session.query(AIService)
                    .filter(
                        AIService.name == ai_import_result.component_name,
                        AIService.app_id == app_id,
                    )
                    .first()
                )
                if imported_service:
                    service_id = imported_service.service_id
                    warnings.extend(ai_import_result.warnings)
            except Exception as e:
                logger.error(f"Failed to import bundled AI service: {e}")
                raise ValueError(
                    f"Failed to import bundled AI service: {e}"
                )
        elif selected_ai_service_id:
            # User selected existing AI service
            service = AIServiceRepository.get_by_id_and_app_id(
                self.session, selected_ai_service_id, app_id
            )
            if not service:
                raise ValueError(
                    f"Selected AI service {selected_ai_service_id} not found"
                )
            service_id = selected_ai_service_id
        elif export_data.agent.service_name:
            # Try to find by name
            service = (
                self.session.query(AIService)
                .filter(
                    AIService.name == export_data.agent.service_name,
                    AIService.app_id == app_id,
                )
                .first()
            )
            if service:
                service_id = service.service_id
            else:
                raise ValueError(
                    f"AI service '{export_data.agent.service_name}' not "
                    f"found and not bundled. Please select an AI service."
                )

        # Step 2: Import or resolve Silo (OPTIONAL)
        silo_id = None
        if export_data.silo:
            # Bundled silo - import it
            try:
                # Use custom name: {original_name} {agent_name}
                silo_custom_name = f"{export_data.silo.name} {agent_name}"
                silo_import_result = self.silo_import.import_silo(
                    export_data,
                    app_id,
                    conflict_mode=ConflictMode.RENAME,
                    new_name=silo_custom_name,
                )
                imported_silo = (
                    self.session.query(Silo)
                    .filter(
                        Silo.name == silo_import_result.component_name,
                        Silo.app_id == app_id,
                    )
                    .first()
                )
                if imported_silo:
                    silo_id = imported_silo.silo_id
                    warnings.extend(silo_import_result.warnings)
            except Exception as e:
                logger.warning(f"Failed to import bundled silo: {e}")
                warnings.append(f"Failed to import bundled silo: {e}")
        elif selected_silo_id:
            # User selected existing silo
            silo = SiloRepository.get_by_id(selected_silo_id, self.session)
            if silo and silo.app_id == app_id:
                silo_id = selected_silo_id
            else:
                warnings.append(
                    f"Selected silo {selected_silo_id} not found"
                )
        elif export_data.agent.silo_name:
            # Try to find by name
            silo = (
                self.session.query(Silo)
                .filter(
                    Silo.name == export_data.agent.silo_name,
                    Silo.app_id == app_id,
                )
                .first()
            )
            if silo:
                silo_id = silo.silo_id
            else:
                warnings.append(
                    f"Silo '{export_data.agent.silo_name}' not found. "
                    f"Agent created without silo."
                )

        # Step 3: Import or resolve Output Parser (OPTIONAL)
        parser_id = None
        if export_data.output_parser:
            # Bundled parser - import it
            try:
                # Use custom name: {original_name} {agent_name}
                parser_custom_name = f"{export_data.output_parser.name} {agent_name}"
                parser_import_result = (
                    self.parser_import.import_output_parser(
                        export_data,
                        app_id,
                        conflict_mode=ConflictMode.RENAME,
                        new_name=parser_custom_name,
                    )
                )
                imported_parser = (
                    self.session.query(OutputParser)
                    .filter(
                        OutputParser.name
                        == parser_import_result.component_name,
                        OutputParser.app_id == app_id,
                    )
                    .first()
                )
                if imported_parser:
                    parser_id = imported_parser.parser_id
                    warnings.extend(parser_import_result.warnings)
            except Exception as e:
                logger.warning(f"Failed to import bundled parser: {e}")
                warnings.append(f"Failed to import bundled parser: {e}")
        elif selected_output_parser_id:
            # User selected existing parser
            parser_repo = OutputParserRepository()
            parser = parser_repo.get_by_id_and_app_id(
                self.session, selected_output_parser_id, app_id
            )
            if parser:
                parser_id = selected_output_parser_id
            else:
                warnings.append(
                    f"Selected parser {selected_output_parser_id} not found"
                )
        elif export_data.agent.output_parser_name:
            # Try to find by name
            parser = (
                self.session.query(OutputParser)
                .filter(
                    OutputParser.name
                    == export_data.agent.output_parser_name,
                    OutputParser.app_id == app_id,
                )
                .first()
            )
            if parser:
                parser_id = parser.parser_id
            else:
                warnings.append(
                    f"Output parser "
                    f"'{export_data.agent.output_parser_name}' not found. "
                    f"Agent created without parser."
                )

        # Step 4: Import bundled MCP configs
        imported_mcp_ids = {}
        for mcp_config in export_data.mcp_configs:
            try:
                mcp_import_result = self.mcp_import.import_mcp_config(
                    export_data,
                    app_id,
                    ConflictMode.RENAME,
                )
                imported_mcp = (
                    self.session.query(MCPConfig)
                    .filter(
                        MCPConfig.name == mcp_import_result.component_name,
                        MCPConfig.app_id == app_id,
                    )
                    .first()
                )
                if imported_mcp:
                    imported_mcp_ids[mcp_config.name] = (
                        imported_mcp.config_id
                    )
                    warnings.extend(mcp_import_result.warnings)
            except Exception as e:
                logger.warning(f"Failed to import MCP config: {e}")
                warnings.append(f"Failed to import MCP config: {e}")

        # Step 5: Import bundled agent tools
        imported_tool_ids = {}
        for tool_agent in export_data.agent_tools:
            try:
                # Create a minimal export file for the tool agent
                from schemas.export_schemas import (
                    AgentExportFileSchema,
                    ExportMetadataSchema,
                )

                tool_export_data = AgentExportFileSchema(
                    metadata=export_data.metadata,
                    agent=tool_agent,
                    ai_service=export_data.ai_service,  # Share AI service
                )
                tool_import_result = self.import_agent(
                    tool_export_data,
                    app_id,
                    ConflictMode.RENAME,
                    selected_ai_service_id=service_id,
                )
                imported_tool = (
                    self.session.query(Agent)
                    .filter(
                        Agent.name == tool_import_result.component_name,
                        Agent.app_id == app_id,
                    )
                    .first()
                )
                if imported_tool:
                    imported_tool_ids[tool_agent.name] = (
                        imported_tool.agent_id
                    )
                    warnings.extend(tool_import_result.warnings)
            except Exception as e:
                logger.warning(f"Failed to import tool agent: {e}")
                warnings.append(f"Failed to import tool agent: {e}")

        # Step 6: Handle existing agent (name already resolved in Step 0)
        if existing_agent and conflict_mode == ConflictMode.RENAME:
            warnings.append(
                f"Agent renamed to '{agent_name}' to avoid conflict"
            )
        
        if existing_agent and conflict_mode == ConflictMode.OVERRIDE:
                # Update existing agent configuration
                existing_agent.description = export_data.agent.description
                existing_agent.system_prompt = (
                    export_data.agent.system_prompt
                )
                existing_agent.prompt_template = (
                    export_data.agent.prompt_template
                )
                existing_agent.service_id = service_id
                existing_agent.silo_id = silo_id
                existing_agent.output_parser_id = parser_id
                existing_agent.has_memory = export_data.agent.has_memory
                existing_agent.memory_max_messages = (
                    export_data.agent.memory_max_messages
                )
                existing_agent.memory_max_tokens = (
                    export_data.agent.memory_max_tokens
                )
                existing_agent.memory_summarize_threshold = (
                    export_data.agent.memory_summarize_threshold
                )
                existing_agent.temperature = export_data.agent.temperature
                
                # Update OCR-specific fields if present
                if hasattr(existing_agent, 'vision_system_prompt'):
                    existing_agent.vision_system_prompt = (
                        export_data.agent.vision_system_prompt
                    )
                if hasattr(existing_agent, 'text_system_prompt'):
                    existing_agent.text_system_prompt = (
                        export_data.agent.text_system_prompt
                    )

                # Update tool associations
                self._update_agent_tools(
                    existing_agent.agent_id,
                    export_data.agent.agent_tool_refs,
                    imported_tool_ids,
                    app_id,
                )

                # Update MCP associations
                self._update_agent_mcps(
                    existing_agent.agent_id,
                    export_data.agent.agent_mcp_refs,
                    imported_mcp_ids,
                    app_id,
                )

                self.session.commit()
                warnings.append(
                    "Existing agent configuration updated. "
                    "Conversation history preserved."
                )

                return ImportSummarySchema(
                    component_type=ComponentType.AGENT,
                    component_name=agent_name,
                    warnings=warnings,
                )

        # Step 7: Create new agent
        # Determine agent type based on OCR fields
        agent_type = "agent"
        if export_data.agent.vision_system_prompt or export_data.agent.text_system_prompt:
            agent_type = "ocr_agent"
        
        if agent_type == "ocr_agent":
            # Import OCRAgent model
            from models.ocr_agent import OCRAgent
            
            # Resolve vision service if specified
            vision_service_id = None
            if export_data.agent.vision_service_name:
                vision_service = (
                    self.session.query(AIService)
                    .filter(
                        AIService.name == export_data.agent.vision_service_name,
                        AIService.app_id == app_id,
                    )
                    .first()
                )
                if vision_service:
                    vision_service_id = vision_service.service_id
            
            new_agent = OCRAgent(
                app_id=app_id,
                name=agent_name,
                description=export_data.agent.description,
                system_prompt=export_data.agent.system_prompt,
                prompt_template=export_data.agent.prompt_template,
                service_id=service_id,
                silo_id=silo_id,
                output_parser_id=parser_id,
                has_memory=export_data.agent.has_memory,
                memory_max_messages=export_data.agent.memory_max_messages,
                memory_max_tokens=export_data.agent.memory_max_tokens,
                memory_summarize_threshold=(
                    export_data.agent.memory_summarize_threshold
                ),
                temperature=export_data.agent.temperature,
                vision_service_id=vision_service_id,
                vision_system_prompt=export_data.agent.vision_system_prompt,
                text_system_prompt=export_data.agent.text_system_prompt,
                create_date=datetime.now(),
                request_count=0,
                is_tool=False,
            )
        else:
            new_agent = Agent(
                app_id=app_id,
                name=agent_name,
                description=export_data.agent.description,
                system_prompt=export_data.agent.system_prompt,
                prompt_template=export_data.agent.prompt_template,
                service_id=service_id,
                silo_id=silo_id,
                output_parser_id=parser_id,
                has_memory=export_data.agent.has_memory,
                memory_max_messages=export_data.agent.memory_max_messages,
                memory_max_tokens=export_data.agent.memory_max_tokens,
                memory_summarize_threshold=(
                    export_data.agent.memory_summarize_threshold
                ),
                temperature=export_data.agent.temperature,
                create_date=datetime.now(),
                request_count=0,
                is_tool=False,
                type="agent",
            )

        self.session.add(new_agent)
        self.session.flush()

        # Step 8: Create tool associations
        self._update_agent_tools(
            new_agent.agent_id,
            export_data.agent.agent_tool_refs,
            imported_tool_ids,
            app_id,
        )

        # Step 9: Create MCP associations
        self._update_agent_mcps(
            new_agent.agent_id,
            export_data.agent.agent_mcp_refs,
            imported_mcp_ids,
            app_id,
        )

        self.session.commit()

        return ImportSummarySchema(
            component_type=ComponentType.AGENT,
            component_name=agent_name,
            warnings=warnings,
        )

    def _update_agent_tools(
        self,
        agent_id: int,
        tool_refs: List,
        imported_tool_ids: Dict[str, int],
        app_id: int,
    ):
        """Update agent tool associations."""
        # Remove existing associations
        existing_assocs = AgentRepository.get_agent_tool_associations(
            self.session, agent_id
        )
        for assoc in existing_assocs:
            AgentRepository.delete_agent_tool_association(
                self.session, assoc
            )

        # Create new associations
        for tool_ref in tool_refs:
            tool_id = None

            # Check if tool was imported
            if tool_ref.tool_agent_name in imported_tool_ids:
                tool_id = imported_tool_ids[tool_ref.tool_agent_name]
            else:
                # Try to find by name
                tool_agent = (
                    self.session.query(Agent)
                    .filter(
                        Agent.name == tool_ref.tool_agent_name,
                        Agent.app_id == app_id,
                    )
                    .first()
                )
                if tool_agent:
                    tool_id = tool_agent.agent_id

            if tool_id:
                AgentRepository.create_agent_tool_association(
                    self.session, agent_id, tool_id
                )

    def _update_agent_mcps(
        self,
        agent_id: int,
        mcp_refs: List,
        imported_mcp_ids: Dict[str, int],
        app_id: int,
    ):
        """Update agent MCP associations."""
        # Remove existing associations
        existing_assocs = AgentRepository.get_agent_mcp_associations(
            self.session, agent_id
        )
        for assoc in existing_assocs:
            AgentRepository.delete_agent_mcp_association(
                self.session, assoc
            )

        # Create new associations
        for mcp_ref in mcp_refs:
            mcp_id = None

            # Check if MCP was imported
            if mcp_ref.mcp_name in imported_mcp_ids:
                mcp_id = imported_mcp_ids[mcp_ref.mcp_name]
            else:
                # Try to find by name
                mcp_config = (
                    self.session.query(MCPConfig)
                    .filter(
                        MCPConfig.name == mcp_ref.mcp_name,
                        MCPConfig.app_id == app_id,
                    )
                    .first()
                )
                if mcp_config:
                    mcp_id = mcp_config.config_id

            if mcp_id:
                AgentRepository.create_agent_mcp_association(
                    self.session, agent_id, mcp_id
                )
