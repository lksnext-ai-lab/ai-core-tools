from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form, Query
from sqlalchemy.orm import Session
from typing import Optional

# Import Pydantic models and auth
from .schemas import (
    AttachFileResponseSchema, 
    DetachFileResponseSchema, 
    ListFilesResponseSchema,
    FileAttachmentSchema
)
from .auth import get_api_key_auth, validate_api_key_for_app
from db.database import get_db

# Import file management service
from services.file_management_service import FileManagementService, FileReference
from services.agent_service import AgentService
from services.conversation_service import ConversationService

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

files_router = APIRouter()


def _create_api_key_user_context(app_id: int, api_key: str, conversation_id: str = None) -> dict:
    """
    Create user context for API key authentication.
    Uses a hash of the API key as user identifier to maintain session isolation.
    
    Args:
        app_id: Application ID
        api_key: API key for authentication
        conversation_id: Optional conversation ID for memory-enabled agents
    """
    import hashlib
    # Use first 16 chars of SHA256 hash for user_id to ensure uniqueness
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    
    return {
        "user_id": f"apikey_{api_key_hash}",
        "app_id": app_id,
        "oauth": False,
        "api_key": api_key,
        "conversation_id": conversation_id
    }


# FILE OPERATION ENDPOINTS

@files_router.post("/{agent_id}/attach-file",
                   summary="Attach file for chat",
                   tags=["File Operations"],
                   response_model=AttachFileResponseSchema)
async def attach_file(
    app_id: int,
    agent_id: int,
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None, description="Optional conversation ID for memory-enabled agents. If not provided for a memory-enabled agent, a new conversation will be created."),
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """
    Attach a file to an agent for chat context.
    
    The file will be processed and stored for use in subsequent chat calls.
    Supported file types: PDF, TXT, MD, JSON, CSV, images (JPG, PNG, etc.)
    
    **For agents with memory:**
    - If conversation_id is provided, the file is associated with that specific conversation
    - If conversation_id is NOT provided, a new conversation is auto-created
    - The conversation_id is returned in the response - use it for subsequent calls
    
    **For agents without memory:**
    - conversation_id is optional (files are session-global)
    """
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        # Get agent to check if it has memory
        agent_service = AgentService()
        agent = agent_service.get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Create base user context for API key user
        user_context = _create_api_key_user_context(app_id, api_key, conversation_id)
        
        # For agents WITH memory: ensure we have a conversation_id
        effective_conversation_id = conversation_id
        
        if agent.has_memory and not conversation_id:
            # Auto-create a conversation for memory-enabled agents
            new_conversation = ConversationService.create_conversation(
                db=db,
                agent_id=agent_id,
                user_context=user_context,
                title=None  # Auto-generate
            )
            effective_conversation_id = str(new_conversation.conversation_id)
            user_context["conversation_id"] = effective_conversation_id
            logger.info(f"Auto-created conversation {effective_conversation_id} for file attachment to agent {agent_id}")
        
        # Use FileManagementService to handle the upload
        file_service = FileManagementService()
        file_ref = await file_service.upload_file(
            file=file,
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=effective_conversation_id
        )
        
        logger.info(f"File {file.filename} attached to agent {agent_id}, conversation {effective_conversation_id} via public API")
        
        return AttachFileResponseSchema(
            success=True,
            file_id=file_ref.file_id,
            filename=file_ref.filename,
            file_type=file_ref.file_type,
            message="File attached successfully",
            conversation_id=effective_conversation_id,  # Return so user can continue with this conversation
            # Visual feedback fields
            file_size_bytes=file_ref.file_size_bytes,
            file_size_display=FileReference.format_file_size(file_ref.file_size_bytes),
            processing_status=file_ref.processing_status,
            content_preview=file_ref.content_preview,
            has_extractable_content=file_ref.has_extractable_content,
            mime_type=file_ref.mime_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error attaching file for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to attach file: {str(e)}")


@files_router.delete("/{agent_id}/detach-file/{file_id}",
                     summary="Remove attached file",
                     tags=["File Operations"],
                     response_model=DetachFileResponseSchema)
async def detach_file(
    app_id: int,
    agent_id: int,
    file_id: str,
    conversation_id: Optional[str] = Query(None, description="Optional conversation ID to scope file removal"),
    api_key: str = Depends(get_api_key_auth)
):
    """
    Remove an attached file from an agent's context.
    
    The file will no longer be included in subsequent chat calls.
    
    **For agents with memory:**
    - If conversation_id is provided, removes the file from that specific conversation
    - If conversation_id is not provided, removes from the global session
    """
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        # Create user context for API key user
        user_context = _create_api_key_user_context(app_id, api_key, conversation_id)
        
        # Use FileManagementService to remove the file
        file_service = FileManagementService()
        success = await file_service.remove_file(
            file_id=file_id,
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=conversation_id
        )
        
        if success:
            logger.info(f"File {file_id} detached from agent {agent_id} via public API")
            return DetachFileResponseSchema(
                success=True,
                message="File detached successfully"
            )
        else:
            return DetachFileResponseSchema(
                success=False,
                message="File not found or already removed"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error detaching file {file_id} for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to detach file: {str(e)}")


@files_router.get("/{agent_id}/attached-files",
                  summary="List attached files",
                  tags=["File Operations"],
                  response_model=ListFilesResponseSchema)
async def list_attached_files(
    app_id: int,
    agent_id: int,
    conversation_id: Optional[str] = Query(None, description="Optional conversation ID to filter files"),
    api_key: str = Depends(get_api_key_auth)
):
    """
    List all files attached to an agent for the current session.
    
    Returns a list of files that will be included in chat context.
    
    **For agents with memory:**
    - If conversation_id is provided, returns only files for that conversation
    - If conversation_id is not provided, returns files from the global session
    """
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        # Create user context for API key user
        user_context = _create_api_key_user_context(app_id, api_key, conversation_id)
        
        # Use FileManagementService to list files
        file_service = FileManagementService()
        files_data = await file_service.list_attached_files(
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=conversation_id
        )
        
        # Convert to schema format with visual feedback data
        files = [
            FileAttachmentSchema(
                file_id=f['file_id'],
                filename=f['filename'],
                file_type=f['file_type'],
                uploaded_at=f.get('uploaded_at'),
                # Visual feedback fields
                file_size_bytes=f.get('file_size_bytes'),
                file_size_display=f.get('file_size_display'),
                processing_status=f.get('processing_status'),
                content_preview=f.get('content_preview'),
                has_extractable_content=f.get('has_extractable_content'),
                mime_type=f.get('mime_type'),
                conversation_id=f.get('conversation_id')
            )
            for f in files_data
        ]
        
        # Calculate total size
        total_size = sum(f.get('file_size_bytes', 0) or 0 for f in files_data)
        
        logger.info(f"Listed {len(files)} files for agent {agent_id} via public API")
        return ListFilesResponseSchema(
            files=files,
            total_size_bytes=total_size,
            total_size_display=FileReference.format_file_size(total_size)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing files for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")
