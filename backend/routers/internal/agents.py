from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from utils.security import generate_signature
import os
from typing import Annotated, Any, List, Optional
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
import json

from services.agent_service import AgentService
from services.agent_export_service import AgentExportService
from services.agent_import_service import AgentImportService
from services.mcp_server_service import MCPServerService
from services.marketplace_service import MarketplaceService
from services.marketplace_quota_service import MarketplaceQuotaService
from services.system_settings_service import SystemSettingsService
from services.user_service import UserService
from db.database import get_db
from schemas.agent_schemas import AgentListItemSchema, AgentDetailSchema, CreateUpdateAgentSchema, UpdatePromptSchema
from schemas.chat_schemas import ChatResponseSchema, ResetResponseSchema, ConversationHistorySchema
from schemas.import_schemas import (
    ConflictMode,
    ImportResponseSchema,
    AgentImportPreviewSchema,
)
from schemas.export_schemas import AgentExportFileSchema
from schemas.marketplace_schemas import (
    MarketplaceVisibilityUpdateSchema,
    MarketplaceProfileCreateUpdateSchema,
    MarketplaceProfileSchema,
)
from services.agent_execution_service import AgentExecutionService
from services.agent_streaming_service import AgentStreamingService
from services.file_management_service import FileManagementService, FileReference
from routers.internal.auth_utils import get_current_user_oauth
from routers.controls.file_size_limit import enforce_file_size_limit
from routers.controls.role_authorization import require_min_role, AppRole
from models.agent import MarketplaceVisibility

from utils.logger import get_logger

logger = get_logger(__name__)

agents_router = APIRouter()

AGENT_NOT_FOUND_ERROR = "Agent not found"
INTERNAL_SERVER_ERROR = "Internal server error"

#DEPENDENCIES

def get_agent_service() -> AgentService:
    """Dependency to get AgentService instance"""
    return AgentService()


def _get_agent_or_404(db: Session, agent_id: int):
    """Get agent by ID or raise 404."""
    agent = AgentService().get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=AGENT_NOT_FOUND_ERROR)
    return agent


def _get_user_from_auth_context(db: Session, auth_context: AuthContext):
    """Get user from auth context identity."""
    return UserService.get_user_by_id(db, int(auth_context.identity.id))


def _check_marketplace_quota(agent, auth_context: AuthContext, db: Session) -> None:
    """Check if user has exceeded the marketplace call quota for public agents.

    Raises HTTPException 429 if quota is exceeded.
    """
    if agent.marketplace_visibility != MarketplaceVisibility.PUBLIC:
        return
    user = _get_user_from_auth_context(db, auth_context)
    if not user or MarketplaceQuotaService.is_user_exempt(user):
        return
    settings_service = SystemSettingsService(db)
    quota_value = settings_service.get_setting("marketplace_call_quota")
    if quota_value and int(quota_value) > 0:
        quota = int(quota_value)
        if MarketplaceQuotaService.check_quota_exceeded(user.user_id, db, quota):
            current_usage = MarketplaceQuotaService.get_current_month_usage(user.user_id, db)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Marketplace call quota exceeded for this month. "
                    f"Current usage: {current_usage}/{quota}. "
                    "Quota resets at the start of next month (UTC)."
                ),
            )


def _try_increment_marketplace_usage(agent, auth_context: AuthContext, db: Session) -> None:
    """Increment marketplace usage counter for public agents when applicable."""
    if agent.marketplace_visibility != MarketplaceVisibility.PUBLIC:
        return
    user = _get_user_from_auth_context(db, auth_context)
    if not user or MarketplaceQuotaService.is_user_exempt(user):
        return
    try:
        MarketplaceQuotaService.increment_usage(user.user_id, db)
        logger.debug(f"Incremented marketplace usage for user {user.user_id}")
    except Exception as e:
        logger.error(f"Failed to increment marketplace usage for user {user.user_id}: {e}")


class ImportOptions:
    """Grouped import query parameters for the import endpoint."""

    def __init__(
        self,
        conflict_mode: Annotated[ConflictMode, Query()] = ConflictMode.FAIL,
        new_name: Annotated[Optional[str], Query()] = None,
        selected_ai_service_id: Annotated[Optional[int], Query()] = None,
        selected_silo_id: Annotated[Optional[int], Query()] = None,
        selected_output_parser_id: Annotated[Optional[int], Query()] = None,
        import_bundled_silo: Annotated[bool, Query()] = True,
        import_bundled_output_parser: Annotated[bool, Query()] = True,
        import_bundled_mcp_configs: Annotated[bool, Query()] = True,
        import_bundled_agent_tools: Annotated[bool, Query()] = True,
    ):
        self.conflict_mode = conflict_mode
        self.new_name = new_name
        self.selected_ai_service_id = selected_ai_service_id
        self.selected_silo_id = selected_silo_id
        self.selected_output_parser_id = selected_output_parser_id
        self.import_bundled_silo = import_bundled_silo
        self.import_bundled_output_parser = import_bundled_output_parser
        self.import_bundled_mcp_configs = import_bundled_mcp_configs
        self.import_bundled_agent_tools = import_bundled_agent_tools


#AGENT MANAGEMENT

@agents_router.post(
    "/preview-import",
    summary="Preview Agent Import",
    tags=["Agents", "Export/Import"],
    response_model=AgentImportPreviewSchema,
)
async def preview_import_agent(
    app_id: int,
    file: Annotated[UploadFile, File()],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    db: Annotated[Session, Depends(get_db)],
):
    """Preview agent import without importing.

    Parses the export file and returns a structured preview with
    conflict detection, dependency info, and warnings. Read-only.
    """
    try:
        content = await file.read()
        file_data = json.loads(content)
        export_data = AgentExportFileSchema(**file_data)

        import_service = AgentImportService(db)
        return import_service.preview_import(export_data, app_id)
    except ValueError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Invalid export file: {e}",
        )
    except Exception as e:
        logger.error(
            f"Preview import error: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Preview failed",
        )


@agents_router.post("/import",
                   summary="Import Agent",
                   tags=["Agents", "Export/Import"],
                   response_model=ImportResponseSchema,
                   status_code=status.HTTP_201_CREATED)
async def import_agent(
    app_id: int,
    file: Annotated[UploadFile, File()],
    import_options: Annotated[ImportOptions, Depends()],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    db: Annotated[Session, Depends(get_db)],
):
    """Import Agent from JSON file.
    
    Note: Conversation history is NOT imported (config only).
    If AI service is not bundled, you must provide selected_ai_service_id.
    """
    try:
        # Parse file
        content = await file.read()
        file_data = json.loads(content)
        export_data = AgentExportFileSchema(**file_data)
        
        # Validate import
        import_service = AgentImportService(db)
        validation = import_service.validate_import(export_data, app_id)
        
        # Check if AI service selection is required but not provided
        if validation.requires_ai_service_selection:
            if import_options.selected_ai_service_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "AI service selection required. "
                        "This agent requires an AI service but none is bundled. "
                        "Please provide selected_ai_service_id parameter."
                    )
                )
        
        # Import
        summary = import_service.import_agent(
            export_data,
            app_id,
            import_options.conflict_mode,
            import_options.new_name,
            import_options.selected_ai_service_id,
            import_options.selected_silo_id,
            import_options.selected_output_parser_id,
            import_bundled_silo=import_options.import_bundled_silo,
            import_bundled_output_parser=import_options.import_bundled_output_parser,
            import_bundled_mcp_configs=import_options.import_bundled_mcp_configs,
            import_bundled_agent_tools=import_options.import_bundled_agent_tools,
        )
        
        return ImportResponseSchema(
            success=True,
            message=f"Agent '{summary.component_name}' imported successfully",
            summary=summary
        )
    except HTTPException:
        raise
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(
                status.HTTP_409_CONFLICT, str(e)
            )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        logger.error(f"Import error: {str(e)}", exc_info=True)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Import failed",
        )


@agents_router.get("/", 
                  summary="List agents",
                  tags=["Agents"],
                  response_model=List[AgentListItemSchema])
async def list_agents(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    db: Annotated[Session, Depends(get_db)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """
    List all agents for a specific app.
    """
    # App access validation would be implemented here
    
    # Get agents using service
    agents_list = agent_service.get_agents_list(db, app_id)
    
    return agents_list


@agents_router.get("/{agent_id}",
                  summary="Get agent details",
                  tags=["Agents"],
                  response_model=AgentDetailSchema)
async def get_agent(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    db: Annotated[Session, Depends(get_db)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """
    Get detailed information about a specific agent plus form data for editing.
    """
    # App access validation would be implemented here
    
    # Get agent details using service
    agent_detail = agent_service.get_agent_detail(db, app_id, agent_id)
    
    if not agent_detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=AGENT_NOT_FOUND_ERROR
        )
    
    return agent_detail


@agents_router.post("/{agent_id}/export",
                   summary="Export Agent",
                   tags=["Agents", "Export/Import"],
                   response_model=AgentExportFileSchema)
async def export_agent(
    app_id: int,
    agent_id: int,
    include_ai_service: Annotated[bool, Query(description="Bundle AI service in export")] = True,
    include_silo: Annotated[bool, Query(description="Bundle silo in export")] = True,
    include_output_parser: Annotated[bool, Query(description="Bundle output parser in export")] = True,
    include_mcp_configs: Annotated[bool, Query(description="Bundle MCP configs in export")] = True,
    include_agent_tools: Annotated[bool, Query(description="Bundle agent tools in export")] = True,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)] = None,
    role: Annotated[AppRole, Depends(require_min_role("viewer"))] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """Export Agent configuration (conversation history NOT included).
    
    Customize which dependencies to bundle:
    - include_ai_service: Bundle the AI service configuration
    - include_silo: Bundle the silo configuration
    - include_output_parser: Bundle the output parser configuration
    - include_mcp_configs: Bundle all MCP configurations
    - include_agent_tools: Bundle all agent tool (other agents) configurations
    """
    try:
        export_service = AgentExportService(db)
        export_data = export_service.export_agent(
            agent_id=agent_id,
            app_id=app_id,
            user_id=int(auth_context.identity.id),
            include_ai_service=include_ai_service,
            include_silo=include_silo,
            include_output_parser=include_output_parser,
            include_mcp_configs=include_mcp_configs,
            include_agent_tools=include_agent_tools,
        )
        return export_data
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except Exception as e:
        logger.error(f"Export error: {str(e)}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Export failed")


@agents_router.post("/{agent_id}",
                   summary="Create or update agent",
                   tags=["Agents"],
                   response_model=AgentDetailSchema)
async def create_or_update_agent(
    app_id: int,
    agent_id: int,
    agent_data: CreateUpdateAgentSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
    db: Annotated[Session, Depends(get_db)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """
    Create a new agent or update an existing one.
    """
    # App access validation would be implemented here
    
    # Prepare agent data
    agent_dict = {
        'agent_id': agent_id,
        'app_id': app_id,
        'name': agent_data.name,
        'description': agent_data.description,
        'system_prompt': agent_data.system_prompt,
        'prompt_template': agent_data.prompt_template,
        'type': agent_data.type,
        'is_tool': agent_data.is_tool,
        'has_memory': agent_data.has_memory,
        'enable_code_interpreter': agent_data.enable_code_interpreter,
        'server_tools': agent_data.server_tools or [],
        'memory_max_messages': agent_data.memory_max_messages,
        'memory_max_tokens': agent_data.memory_max_tokens,
        'memory_summarize_threshold': agent_data.memory_summarize_threshold,
        'service_id': agent_data.service_id,
        'silo_id': agent_data.silo_id,
        'output_parser_id': agent_data.output_parser_id,
        'temperature': agent_data.temperature,
        # OCR-specific fields
        'vision_service_id': agent_data.vision_service_id,
        'vision_system_prompt': agent_data.vision_system_prompt,
        'text_system_prompt': agent_data.text_system_prompt
    }
    
    logger.info(f"Creating/updating agent with data: {agent_dict}")
    
    # Create or update agent
    created_agent_id = agent_service.create_or_update_agent(db, agent_dict, agent_data.type)
    
    # Update tools, MCPs, and skills (always call to handle empty arrays for unselecting)
    agent_service.update_agent_tools(db, created_agent_id, agent_data.tool_ids, {})
    agent_service.update_agent_mcps(db, created_agent_id, agent_data.mcp_config_ids, {})
    agent_service.update_agent_skills(db, created_agent_id, agent_data.skill_ids, {})

    # Return updated agent (reuse the GET logic)
    return await get_agent(app_id, created_agent_id, auth_context, role, db, agent_service)


@agents_router.delete("/{agent_id}",
                     summary="Delete agent",
                     tags=["Agents"])
async def delete_agent(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
    db: Annotated[Session, Depends(get_db)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """
    Delete an agent.
    """
    # App access validation would be implemented here

    # Check if agent exists
    agent = agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=AGENT_NOT_FOUND_ERROR
        )

    # Delete agent
    success = agent_service.delete_agent(db, agent_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete agent"
        )

    return {"message": "Agent deleted successfully"}


@agents_router.get("/{agent_id}/mcp-usage",
                   summary="Get MCP servers using this agent",
                   tags=["Agents"])
async def get_agent_mcp_usage(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    db: Annotated[Session, Depends(get_db)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """
    Get list of MCP servers that use this agent.
    Used to warn users before unmarking an agent as tool or deleting it.
    """
    # Check if agent exists
    agent = agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=AGENT_NOT_FOUND_ERROR
        )

    # Get MCP servers using this agent
    servers = MCPServerService.get_mcp_servers_using_agent(db, agent_id)

    return {
        "agent_id": agent_id,
        "is_tool": agent.is_tool,
        "mcp_servers": servers,
        "used_in_mcp_servers": len(servers) > 0
    }


@agents_router.post("/{agent_id}/update-prompt",
                   summary="Update agent prompt",
                   tags=["Agents"])
async def update_agent_prompt(
    app_id: int,
    agent_id: int,
    prompt_data: UpdatePromptSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """
    Update agent system prompt or prompt template.
    """
    # Validate prompt type
    if prompt_data.type not in ['system', 'template']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid prompt type. Must be 'system' or 'template'"
        )
    
    # Update prompt using service
    success = agent_service.update_agent_prompt(db, agent_id, prompt_data.type, prompt_data.prompt)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=AGENT_NOT_FOUND_ERROR
        )
    
    return {"message": f"{prompt_data.type.capitalize()} prompt updated successfully"}


# ==================== PLAYGROUND & ANALYTICS ====================

@agents_router.get("/{agent_id}/playground",
                  summary="Get agent playground",
                  tags=["Agents", "Playground"])
async def agent_playground(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """
    Get agent playground interface data.
    """
    # App access validation would be implemented here
    
    playground_data = agent_service.get_agent_playground_data(db, agent_id)
    
    if not playground_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=AGENT_NOT_FOUND_ERROR
        )
    
    return playground_data


@agents_router.get("/{agent_id}/analytics",
                  summary="Get agent analytics",
                  tags=["Agents", "Analytics"])
async def agent_analytics(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """
    Get agent analytics data (premium feature).
    """
    # App access validation would be implemented here
    # Premium feature check would be implemented here
    
    analytics_data = agent_service.get_agent_analytics(db, agent_id)
    
    if not analytics_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=AGENT_NOT_FOUND_ERROR
        )
    
    return analytics_data


# ==================== CHAT ENDPOINTS ====================


def _parse_optional_json(value: Optional[str], param_name: str) -> Any:
    """Parse a JSON-encoded optional string, logging a warning on decode failure."""
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        logger.warning(f"Invalid {param_name} JSON, ignoring")
        return None


def _extract_jwt_token(request: Request) -> Optional[str]:
    """Extract the JWT bearer token from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    return None


async def _resolve_chat_file_refs(
    files: Optional[List[UploadFile]],
    parsed_file_references: Optional[list],
    agent_id: int,
    user_context: dict,
    conversation_id: Optional[int],
) -> List[FileReference]:
    """Collect and resolve file references for a chat request."""
    file_service = FileManagementService()
    all_refs: List[FileReference] = []
    uploaded_ids: set = set()

    if files:
        for upload_file in files:
            if upload_file.filename:
                file_ref = await file_service.upload_file(
                    file=upload_file,
                    agent_id=agent_id,
                    user_context=user_context,
                    conversation_id=conversation_id,
                )
                all_refs.append(file_ref)
                uploaded_ids.add(file_ref.file_id)

    existing_files = await file_service.list_attached_files(
        agent_id=agent_id,
        user_context=user_context,
        conversation_id=str(conversation_id) if conversation_id else None,
    )

    if parsed_file_references:
        requested_ids = set(parsed_file_references)
        existing_files = [f for f in existing_files if f["file_id"] in requested_ids]
        logger.info(f"Filtered to {len(existing_files)} files based on file_references")

    for file_data in existing_files:
        if file_data["file_id"] not in uploaded_ids:
            all_refs.append(
                FileReference(
                    file_id=file_data["file_id"],
                    filename=file_data["filename"],
                    file_type=file_data["file_type"],
                    content=file_data["content"],
                    file_path=file_data.get("file_path"),
                )
            )

    return all_refs


async def _save_uploaded_file(upload_file: UploadFile) -> str:
    """Save uploaded file to temporary location and return file path"""
    import asyncio
    import tempfile

    from utils.config import get_app_config
    app_config = get_app_config()
    tmp_base_folder = app_config['TMP_BASE_FOLDER']
    uploads_dir = os.path.join(tmp_base_folder, "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    suffix = os.path.splitext(upload_file.filename)[1] if upload_file.filename else ''
    content = await upload_file.read()

    def _write_temp(data: bytes) -> str:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=uploads_dir) as tf:
            tf.write(data)
            return tf.name

    return await asyncio.get_event_loop().run_in_executor(None, _write_temp, content)


@agents_router.post(
    "/{agent_id}/chat",
    summary="Chat with agent",
    tags=["Agents"],
    response_model=ChatResponseSchema,
    responses={
        404: {"description": "Agent not found"},
        429: {"description": "Marketplace call quota exceeded"},
        500: {"description": "Internal server error"},
    },
)
async def chat_with_agent(
    app_id: int,
    agent_id: int,
    request: Request,
    message: Annotated[str, Form()],
    files: Annotated[Optional[List[UploadFile]], File()] = None,
    file_references: Annotated[Optional[str], Form()] = None,
    search_params: Annotated[Optional[str], Form()] = None,
    conversation_id: Annotated[Optional[int], Form()] = None,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
    _: Annotated[None, Depends(enforce_file_size_limit)] = None,
):
    """
    Internal API: Chat with agent for playground (OAuth authentication)
    
    Args:
        agent_id: ID of the agent
        message: User message
        files: Optional uploaded files
        file_references: Optional JSON array of file_ids to include. If not provided, all files are included.
        search_params: Optional search parameters
        conversation_id: Optional conversation ID to continue existing conversation
    """
    try:
        # Fetch agent to check marketplace visibility
        agent = _get_agent_or_404(db, agent_id)

        # Check marketplace quota enforcement (only for public marketplace agents)
        _check_marketplace_quota(agent, auth_context, db)

        parsed_search_params = _parse_optional_json(search_params, "search_params")
        parsed_file_references = _parse_optional_json(file_references, "file_references")
        if not isinstance(parsed_file_references, list):
            parsed_file_references = None

        jwt_token = _extract_jwt_token(request)
        if jwt_token:
            logger.debug(f"Extracted JWT token for MCP auth (length: {len(jwt_token)})")

        user_context = {
            "user_id": int(auth_context.identity.id),
            "email": auth_context.identity.email,
            "oauth": True,
            "app_id": app_id,
            "token": jwt_token,
        }

        all_file_references = await _resolve_chat_file_refs(
            files, parsed_file_references, agent_id, user_context, conversation_id
        )

        execution_service = AgentExecutionService(db)
        result = await execution_service.execute_agent_chat_with_file_refs(
            agent_id=agent_id,
            message=message,
            file_references=all_file_references,
            search_params=parsed_search_params,
            user_context=user_context,
            conversation_id=conversation_id,
            db=db,
        )

        # Increment marketplace usage counter (if marketplace agent and not exempt)
        _try_increment_marketplace_usage(agent, auth_context, db)

        logger.info(f"Chat request processed for agent {agent_id} by user {auth_context.identity.id}")
        return ChatResponseSchema(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR)


@agents_router.post(
    "/{agent_id}/chat/stream",
    summary="Chat with agent (streaming)",
    tags=["Agents"],
    responses={500: {"description": "Internal server error"}},
)
async def chat_with_agent_stream(
    app_id: int,
    agent_id: int,
    request: Request,
    message: Annotated[str, Form()],
    files: Annotated[Optional[List[UploadFile]], File()] = None,
    file_references: Annotated[Optional[str], Form()] = None,
    search_params: Annotated[Optional[str], Form()] = None,
    conversation_id: Annotated[Optional[int], Form()] = None,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
    _: Annotated[None, Depends(enforce_file_size_limit)] = None,
):
    """
    Internal API: Chat with agent using Server-Sent Events streaming (OAuth authentication)

    Returns a stream of SSE events with types: metadata, token, tool_start, tool_end,
    thinking, done, error.  The playground uses this endpoint for real-time responses.
    """
    try:
        parsed_search_params = _parse_optional_json(search_params, "search_params")
        parsed_file_references = _parse_optional_json(file_references, "file_references")
        if not isinstance(parsed_file_references, list):
            parsed_file_references = None

        jwt_token = _extract_jwt_token(request)

        user_context = {
            "user_id": int(auth_context.identity.id),
            "email": auth_context.identity.email,
            "oauth": True,
            "app_id": app_id,
            "token": jwt_token,
        }

        all_file_references = await _resolve_chat_file_refs(
            files, parsed_file_references, agent_id, user_context, conversation_id
        )

        streaming_service = AgentStreamingService(db)
        generator = streaming_service.stream_agent_chat(
            agent_id=agent_id,
            message=message,
            file_references=all_file_references,
            search_params=parsed_search_params,
            user_context=user_context,
            conversation_id=conversation_id,
            db=db,
        )

        logger.info(f"Streaming chat request for agent {agent_id} by user {auth_context.identity.id}")
        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in streaming chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR)


@agents_router.post(
    "/{agent_id}/reset",
    summary="Reset conversation",
    tags=["Agents"],
    response_model=ResetResponseSchema,
    responses={500: {"description": "Internal server error"}},
)
async def reset_conversation(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Internal API: Reset conversation for playground (OAuth authentication)
    """
    try:
        # Create user context for OAuth user
        user_context = {
            "user_id": int(auth_context.identity.id),
            "oauth": True,
            "app_id": app_id
        }
        
        # Use unified service layer
        execution_service = AgentExecutionService(db)
        success = await execution_service.reset_agent_conversation(
            agent_id=agent_id,
            user_context=user_context,
            db=db
        )
        
        if success:
            logger.info(f"Conversation reset for agent {agent_id} by user {auth_context.identity.id}")
            return ResetResponseSchema(success=True, message="Conversation reset successfully")
        else:
            return ResetResponseSchema(success=False, message="Failed to reset conversation")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in reset endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR)


@agents_router.get(
    "/{agent_id}/conversation-history",
    summary="Get conversation history",
    tags=["Agents"],
    response_model=ConversationHistorySchema,
    responses={404: {"description": "Agent not found"}, 500: {"description": "Internal server error"}},
)
async def get_conversation_history(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
):
    """
    Internal API: Get conversation history for playground (OAuth authentication)
    """
    try:
        # Get agent to check if it has memory
        agent = agent_service.get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Create user context for OAuth user
        user_context = {
            "user_id": int(auth_context.identity.id),
            "oauth": True,
            "app_id": app_id
        }
        
        # Use unified service layer
        execution_service = AgentExecutionService(db)
        messages = await execution_service.get_conversation_history(
            agent_id=agent_id,
            user_context=user_context,
            db=db
        )
        
        logger.info(f"Retrieved {len(messages)} messages for agent {agent_id} by user {auth_context.identity.id}")
        return ConversationHistorySchema(
            messages=messages,
            agent_id=agent_id,
            has_memory=agent.has_memory
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in conversation history endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR)


@agents_router.post(
    "/{agent_id}/upload-file",
    summary="Upload file for chat",
    tags=["Agents"],
    responses={500: {"description": "File upload failed"}},
)
async def upload_file_for_chat(
    app_id: int,
    agent_id: int,
    file: Annotated[UploadFile, File()],
    conversation_id: Annotated[Optional[int], Form()] = None,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
    _: Annotated[None, Depends(enforce_file_size_limit)] = None,
):
    """
    Internal API: Upload file for chat (OAuth authentication)
    
    Args:
        conversation_id: Optional conversation ID to associate the file with.
                        If provided, file will be specific to that conversation.
    """
    try:
        # Create user context for OAuth user
        user_context = {
            "user_id": int(auth_context.identity.id),
            "oauth": True,
            "app_id": app_id
        }
        
        # Use unified service layer
        file_service = FileManagementService()
        file_ref = await file_service.upload_file(
            file=file,
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=conversation_id
        )
        
        logger.info(f"File uploaded for agent {agent_id} by user {auth_context.identity.id}")
        return {
            "success": True,
            "file_id": file_ref.file_id,
            "filename": file_ref.filename,
            "file_type": file_ref.file_type,
            # Visual feedback fields
            "file_size_bytes": file_ref.file_size_bytes,
            "file_size_display": FileReference.format_file_size(file_ref.file_size_bytes),
            "processing_status": file_ref.processing_status,
            "content_preview": file_ref.content_preview,
            "has_extractable_content": file_ref.has_extractable_content,
            "mime_type": file_ref.mime_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in file upload endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="File upload failed")


@agents_router.get(
    "/{agent_id}/files",
    summary="List attached files",
    tags=["Agents"],
    responses={500: {"description": "Failed to list files"}},
)
async def list_attached_files(
    app_id: int,
    agent_id: int,
    conversation_id: Optional[int] = None,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Internal API: List attached files for chat (OAuth authentication)
    
    Args:
        conversation_id: Optional conversation ID to filter files.
                        If provided, only files for that conversation are returned.
    """
    try:
        # Create user context for OAuth user
        user_context = {
            "user_id": int(auth_context.identity.id),
            "oauth": True,
            "app_id": app_id
        }
        
        # Use unified service layer
        file_service = FileManagementService()
        files = await file_service.list_attached_files(
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=str(conversation_id) if conversation_id else None
        )
        
        # Calculate total size for visual feedback
        total_size = sum(f.get('file_size_bytes', 0) or 0 for f in files)
        
        return {
            "files": files,
            "total_size_bytes": total_size,
            "total_size_display": FileReference.format_file_size(total_size)
        }
        
    except Exception as e:
        logger.error(f"Error in list files endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list files")


@agents_router.delete(
    "/{agent_id}/files/{file_id}",
    summary="Remove attached file",
    tags=["Agents"],
    responses={500: {"description": "Failed to remove file"}},
)
async def remove_attached_file(
    app_id: int,
    agent_id: int,
    file_id: str,
    conversation_id: Optional[int] = None,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Internal API: Remove attached file (OAuth authentication)
    
    Args:
        conversation_id: Optional conversation ID for conversation-specific files.
    """
    try:
        # Create user context for OAuth user
        user_context = {
            "user_id": int(auth_context.identity.id),
            "oauth": True,
            "app_id": app_id
        }
        
        # Use unified service layer
        file_service = FileManagementService()
        success = await file_service.remove_file(
            file_id=file_id,
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=str(conversation_id) if conversation_id else None
        )
        
        if success:
            logger.info(f"File {file_id} removed for agent {agent_id} by user {auth_context.identity.id}")
            return {"success": True, "message": "File removed successfully"}
        else:
            return {"success": False, "message": "File not found or already removed"}
            
    except Exception as e:
        logger.error(f"Error in remove file endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to remove file") 


@agents_router.get(
    "/{agent_id}/files/{file_id}/download",
    summary="Download a file (uploaded or agent-generated)",
    tags=["Agents"],
    responses={404: {"description": "File not found"}, 500: {"description": "File download failed"}},
)
async def download_file(
    app_id: int,
    agent_id: int,
    file_id: str,
    request: Request,
    conversation_id: Optional[int] = None,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Internal API: Download an uploaded or agent-generated file.

    Looks up the file by file_id scoped to the calling user's session,
    returns a signed URL for the /static/ endpoint (no auth required).
    """
    try:
        user_context = {
            "user_id": int(auth_context.identity.id),
            "oauth": True,
            "app_id": app_id
        }

        file_service = FileManagementService()

        # Try with conversation_id first, then fall back to the global session so that
        # files registered before the conversation was known (first-message auto-create)
        # are still resolved correctly.
        file_data = None
        conv_ids_to_try = [str(conversation_id), None] if conversation_id else [None]
        for try_conv_id in conv_ids_to_try:
            files = await file_service.list_attached_files(
                agent_id=agent_id,
                user_context=user_context,
                conversation_id=try_conv_id,
            )
            file_data = next((f for f in files if f.get("file_id") == file_id), None)
            if file_data:
                break

        if not file_data or not file_data.get("file_path"):
            raise HTTPException(status_code=404, detail="File not found")

        file_path = file_data["file_path"].lstrip("/")
        filename = file_data.get("filename", os.path.basename(file_path))
        user_email = auth_context.identity.email

        # Build absolute base URL: prefer explicit env var, fall back to request origin
        aict_base_url = os.getenv("AICT_BASE_URL", "").rstrip("/")
        if not aict_base_url:
            aict_base_url = str(request.base_url).rstrip("/")

        sig = generate_signature(file_path, user_email)
        download_url = (
            f"{aict_base_url}/static/{file_path}"
            f"?user={user_email}&sig={sig}"
            f"&filename={filename}"
        )

        return {"download_url": download_url, "filename": filename}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in download file endpoint: {e}")
        raise HTTPException(status_code=500, detail="File download failed")


# ==================== MARKETPLACE MANAGEMENT ====================


@agents_router.put("/{agent_id}/marketplace-visibility",
                   summary="Update marketplace visibility",
                   tags=["Agents", "Marketplace"])
async def update_marketplace_visibility(
    app_id: int,
    agent_id: int,
    data: MarketplaceVisibilityUpdateSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
    db: Annotated[Session, Depends(get_db)],
):
    """Update an agent's marketplace visibility (unpublished/private/public)."""
    try:
        agent = MarketplaceService.update_marketplace_visibility(
            db=db,
            agent_id=agent_id,
            app_id=app_id,
            visibility_str=data.marketplace_visibility,
        )
        return {"marketplace_visibility": agent.marketplace_visibility.value}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@agents_router.get("/{agent_id}/marketplace-profile",
                   summary="Get marketplace profile",
                   tags=["Agents", "Marketplace"],
                   response_model=MarketplaceProfileSchema)
async def get_marketplace_profile(
    app_id: int,
    agent_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    db: Annotated[Session, Depends(get_db)],
):
    """Get the marketplace profile for an agent (EDITOR+ management view)."""
    profile = MarketplaceService.get_marketplace_profile(db, agent_id, app_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace profile not found",
        )
    return profile


@agents_router.put("/{agent_id}/marketplace-profile",
                   summary="Create or update marketplace profile",
                   tags=["Agents", "Marketplace"],
                   response_model=MarketplaceProfileSchema)
async def update_marketplace_profile(
    app_id: int,
    agent_id: int,
    profile_data: MarketplaceProfileCreateUpdateSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
    db: Annotated[Session, Depends(get_db)],
):
    """Create or update the marketplace profile for an agent."""
    try:
        profile = MarketplaceService.create_or_update_marketplace_profile(
            db=db,
            agent_id=agent_id,
            app_id=app_id,
            profile_data=profile_data,
        )
        return MarketplaceProfileSchema.model_validate(profile)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))