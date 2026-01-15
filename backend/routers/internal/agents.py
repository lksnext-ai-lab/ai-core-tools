from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form
from typing import List, Optional
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
import json

from services.agent_service import AgentService
from db.database import get_db
from schemas.agent_schemas import AgentListItemSchema, AgentDetailSchema, CreateUpdateAgentSchema, UpdatePromptSchema
from schemas.chat_schemas import ChatResponseSchema, ResetResponseSchema, ConversationHistorySchema
from services.agent_execution_service import AgentExecutionService
from services.file_management_service import FileManagementService, FileReference
from routers.internal.auth_utils import get_current_user_oauth
from routers.controls.file_size_limit import enforce_file_size_limit
from routers.controls.role_authorization import require_min_role, AppRole

from utils.logger import get_logger

logger = get_logger(__name__)

agents_router = APIRouter()

AGENT_NOT_FOUND_ERROR = "Agent not found"
INTERNAL_SERVER_ERROR = "Internal server error"

#DEPENDENCIES

def get_agent_service() -> AgentService:
    """Dependency to get AgentService instance"""
    return AgentService()

#AGENT MANAGEMENT

@agents_router.get("/", 
                  summary="List agents",
                  tags=["Agents"],
                  response_model=List[AgentListItemSchema])
async def list_agents(
    app_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db),
    agent_service: AgentService = Depends(get_agent_service)
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
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db),
    agent_service: AgentService = Depends(get_agent_service)
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


@agents_router.post("/{agent_id}",
                   summary="Create or update agent",
                   tags=["Agents"],
                   response_model=AgentDetailSchema)
async def create_or_update_agent(
    app_id: int,
    agent_id: int,
    agent_data: CreateUpdateAgentSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("editor")),
    db: Session = Depends(get_db),
    agent_service: AgentService = Depends(get_agent_service)
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
    
    # Update tools and MCPs (always call to handle empty arrays for unselecting)
    agent_service.update_agent_tools(db, created_agent_id, agent_data.tool_ids, {})
    agent_service.update_agent_mcps(db, created_agent_id, agent_data.mcp_config_ids, {})
    
    # Return updated agent (reuse the GET logic)
    return await get_agent(app_id, created_agent_id, auth_context, role, db, agent_service)


@agents_router.delete("/{agent_id}",
                     summary="Delete agent",
                     tags=["Agents"])
async def delete_agent(
    app_id: int, 
    agent_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("editor")),
    db: Session = Depends(get_db),
    agent_service: AgentService = Depends(get_agent_service)
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


@agents_router.post("/{agent_id}/update-prompt",
                   summary="Update agent prompt",
                   tags=["Agents"])
async def update_agent_prompt(
    app_id: int,
    agent_id: int,
    prompt_data: UpdatePromptSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
    agent_service: AgentService = Depends(get_agent_service)
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
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
    agent_service: AgentService = Depends(get_agent_service)
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
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
    agent_service: AgentService = Depends(get_agent_service)
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

async def _save_uploaded_file(upload_file: UploadFile) -> str:
    """Save uploaded file to temporary location and return file path"""
    import tempfile
    import os
    
    # Get TMP_BASE_FOLDER from config
    from utils.config import get_app_config
    app_config = get_app_config()
    tmp_base_folder = app_config['TMP_BASE_FOLDER']
    uploads_dir = os.path.join(tmp_base_folder, "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    
    # Create temporary file in TMP_BASE_FOLDER/uploads
    suffix = os.path.splitext(upload_file.filename)[1] if upload_file.filename else ''
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=uploads_dir) as temp_file:
        content = await upload_file.read()
        temp_file.write(content)
        temp_file_path = temp_file.name
    
    return temp_file_path


@agents_router.post("/{agent_id}/chat",
                  summary="Chat with agent",
                  tags=["Agents"],
                  response_model=ChatResponseSchema)
async def chat_with_agent(
    app_id: int,
    agent_id: int,
    request: Request,
    message: str = Form(...),
    files: List[UploadFile] = File(None),
    file_references: Optional[str] = Form(None),
    search_params: Optional[str] = Form(None),
    conversation_id: Optional[int] = Form(None),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
    _: None = Depends(enforce_file_size_limit)
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
        # Parse search params if provided
        parsed_search_params = None
        if search_params:
            try:
                parsed_search_params = json.loads(search_params)
            except json.JSONDecodeError:
                logger.warning("Invalid search_params JSON")
        
        # Parse file_references if provided (for filtering which files to include)
        parsed_file_references = None
        if file_references:
            try:
                parsed_file_references = json.loads(file_references)
                if not isinstance(parsed_file_references, list):
                    parsed_file_references = None
            except json.JSONDecodeError:
                logger.warning("Invalid file_references JSON, ignoring")
        
        # Extract JWT token from Authorization header for MCP authentication
        auth_header = request.headers.get('Authorization', '')
        jwt_token = None
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.split(' ')[1]
            logger.debug(f"Extracted JWT token for MCP auth (length: {len(jwt_token)})")
        
        # Create user context for OAuth user
        user_context = {
            "user_id": int(auth_context.identity.id),
            "email": auth_context.identity.email,
            "oauth": True,
            "app_id": app_id,
            "token": jwt_token  # Add JWT token for MCP authentication
        }
        
        # Process files using FileManagementService for persistence
        file_service = FileManagementService()
        all_file_references = []
        uploaded_file_ids = set()  # Track newly uploaded files to avoid duplicates
        
        # Add any new files uploaded with this message
        if files:
            for upload_file in files:
                if upload_file.filename:  # Skip empty file slots
                    # Upload file to persistent storage
                    file_ref = await file_service.upload_file(
                        file=upload_file,
                        agent_id=agent_id,
                        user_context=user_context,
                        conversation_id=conversation_id
                    )
                    all_file_references.append(file_ref)
                    uploaded_file_ids.add(file_ref.file_id)
        
        # Get previously uploaded files for this session/conversation
        existing_files = await file_service.list_attached_files(
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=str(conversation_id) if conversation_id else None
        )
        
        # Filter existing files if file_references was provided
        if parsed_file_references:
            requested_file_ids = set(parsed_file_references)
            existing_files = [f for f in existing_files if f['file_id'] in requested_file_ids]
            logger.info(f"Filtered to {len(existing_files)} files based on file_references")
        
        # Convert existing files to FileReference objects (avoiding duplicates)
        for file_data in existing_files:
            if file_data['file_id'] not in uploaded_file_ids:
                file_ref = FileReference(
                    file_id=file_data['file_id'],
                    filename=file_data['filename'],
                    file_type=file_data['file_type'],
                    content=file_data['content'],
                    file_path=file_data.get('file_path')
                )
                all_file_references.append(file_ref)
        
        # Use unified service layer with file references
        execution_service = AgentExecutionService(db)
        result = await execution_service.execute_agent_chat_with_file_refs(
            agent_id=agent_id,
            message=message,
            file_references=all_file_references,
            search_params=parsed_search_params,
            user_context=user_context,
            conversation_id=conversation_id,
            db=db
        )
        
        logger.info(f"Chat request processed for agent {agent_id} by user {auth_context.identity.id}")
        return ChatResponseSchema(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR)


@agents_router.post("/{agent_id}/reset",
                  summary="Reset conversation",
                  tags=["Agents"],
                  response_model=ResetResponseSchema)
async def reset_conversation(
    app_id: int,
    agent_id: int,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
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


@agents_router.get("/{agent_id}/conversation-history",
                  summary="Get conversation history",
                  tags=["Agents"],
                  response_model=ConversationHistorySchema)
async def get_conversation_history(
    app_id: int,
    agent_id: int,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
    agent_service: AgentService = Depends(get_agent_service)
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


@agents_router.post("/{agent_id}/upload-file",
                  summary="Upload file for chat",
                  tags=["Agents"])
async def upload_file_for_chat(
    app_id: int,
    agent_id: int,
    file: UploadFile = File(...),
    conversation_id: Optional[int] = Form(None),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db),
    _: None = Depends(enforce_file_size_limit)
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


@agents_router.get("/{agent_id}/files",
                 summary="List attached files",
                 tags=["Agents"])
async def list_attached_files(
    app_id: int,
    agent_id: int,
    conversation_id: Optional[int] = None,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
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


@agents_router.delete("/{agent_id}/files/{file_id}",
                    summary="Remove attached file",
                    tags=["Agents"])
async def remove_attached_file(
    app_id: int,
    agent_id: int,
    file_id: str,
    conversation_id: Optional[int] = None,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
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