from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import hashlib
import json

# Import Pydantic models and auth
from .schemas import AgentResponseSchema, MessageResponseSchema
from .auth import get_api_key_auth, validate_api_key_for_app
from db.database import get_db

# Import services
from services.agent_execution_service import AgentExecutionService
from services.file_management_service import FileManagementService, FileReference
from services.agent_service import AgentService
from services.conversation_service import ConversationService

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

chat_router = APIRouter()


def _create_api_key_user_context(app_id: int, api_key: str, conversation_id: str = None) -> dict:
    """
    Create user context for API key authentication.
    Uses a hash of the API key as user identifier to maintain session isolation.
    """
    # Use first 16 chars of SHA256 hash for user_id to ensure uniqueness
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    
    return {
        "user_id": f"apikey_{api_key_hash}",
        "app_id": app_id,
        "oauth": False,
        "api_key": api_key,
        "conversation_id": conversation_id
    }


# AGENT CHAT ENDPOINTS

@chat_router.post("/{agent_id}/call", 
                  summary="Call agent", 
                  tags=["Agent Chat"],
                  response_model=AgentResponseSchema)
async def call_agent(
    app_id: int,
    agent_id: int,
    message: str = Form(..., description="The user message to send to the agent"),
    files: List[UploadFile] = File(None, description="Optional files to attach (images, PDFs, text files)"),
    file_references: Optional[str] = Form(None, description="JSON array of existing file_ids to include. If not provided, all files are included."),
    search_params: Optional[str] = Form(None, description="JSON object with search parameters for silo-based agents"),
    conversation_id: Optional[str] = Form(None, description="Optional conversation ID to continue existing conversation"),
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """
    Call an agent for chat completion.
    
    Supports text messages and file attachments. Files can be:
    - Uploaded directly with this request
    - Previously attached using /files/{agent_id}/attach-file
    
    **Behavior for agents WITH memory:**
    - If conversation_id is not provided, a new conversation is auto-created
    - The conversation_id is returned in the response - use it for subsequent calls
    - Files are always associated with the conversation
    
    **Behavior for agents WITHOUT memory:**
    - conversation_id is optional and used only for file grouping
    - Each call is independent (no memory persistence)
    
    **File handling:**
    - New files uploaded with this request are automatically persisted
    - If file_references is not provided, ALL attached files are included
    - If file_references is provided, only those specific files are included
    
    **Supported file types:**
    - PDF files (.pdf): Text is extracted automatically
    - Text files (.txt, .md, .json, .csv): Content is read directly
    - Images (.jpg, .jpeg, .png, .gif, .bmp): Sent to vision models
    - Documents (.doc, .docx): Basic support
    
    **Usage with curl:**
    ```bash
    # First call (auto-creates conversation for memory-enabled agents)
    curl -X POST "http://your-api/public/v1/app/{app_id}/chat/{agent_id}/call" \\
      -H "X-API-KEY: your-api-key" \\
      -F "message=What is in this document?" \\
      -F "files=@document.pdf"
    # Response includes conversation_id - use it for follow-up calls
    
    # Follow-up call with same conversation
    curl -X POST "http://your-api/public/v1/app/{app_id}/chat/{agent_id}/call" \\
      -H "X-API-KEY: your-api-key" \\
      -F "message=Tell me more about section 3" \\
      -F "conversation_id=123"
    ```
    """
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        # Parse optional JSON parameters
        parsed_search_params = None
        if search_params:
            try:
                parsed_search_params = json.loads(search_params)
            except json.JSONDecodeError:
                logger.warning("Invalid search_params JSON, ignoring")
        
        parsed_file_references = None
        if file_references:
            try:
                parsed_file_references = json.loads(file_references)
                if not isinstance(parsed_file_references, list):
                    parsed_file_references = None
            except json.JSONDecodeError:
                logger.warning("Invalid file_references JSON, ignoring")
        
        # Get agent to check if it has memory
        agent_service = AgentService()
        agent = agent_service.get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Create base user context for API key user
        user_context = _create_api_key_user_context(app_id, api_key, conversation_id)
        
        # For agents WITH memory: ensure we have a conversation_id
        # This ensures files and memory are always linked to the same conversation
        effective_conversation_id = conversation_id or "temp"  # Default for agents without memory
        db_conversation_id = None  # Integer ID for database operations
        
        if agent.has_memory:
            if conversation_id:
                # User provided a conversation_id - try to find it
                # The conversation_id from API could be either the DB id or a custom identifier
                try:
                    db_conversation_id = int(conversation_id)
                    existing_conv = ConversationService.get_conversation(
                        db=db,
                        conversation_id=db_conversation_id,
                        user_context=user_context
                    )
                    if not existing_conv:
                        raise HTTPException(status_code=404, detail="Conversation not found or access denied")
                    effective_conversation_id = str(db_conversation_id)
                except ValueError:
                    # conversation_id is not an integer - treat as custom identifier
                    # Files will be stored with this custom identifier
                    effective_conversation_id = conversation_id
                    db_conversation_id = None
            else:
                # No conversation_id provided - auto-create one for memory-enabled agents
                new_conversation = ConversationService.create_conversation(
                    db=db,
                    agent_id=agent_id,
                    user_context=user_context,
                    title=None  # Auto-generate
                )
                db_conversation_id = new_conversation.conversation_id
                effective_conversation_id = str(db_conversation_id)
                logger.info(f"Auto-created conversation {db_conversation_id} for memory-enabled agent {agent_id}")
        
        # Update user context with the effective conversation_id
        user_context["conversation_id"] = effective_conversation_id
        
        # Initialize file service
        file_service = FileManagementService()
        all_file_references = []
        uploaded_file_ids = set()  # Track newly uploaded files to avoid duplicates
        
        # Process newly uploaded files (persist them with conversation context)
        if files:
            for upload_file in files:
                if upload_file.filename:  # Skip empty file slots
                    try:
                        file_ref = await file_service.upload_file(
                            file=upload_file,
                            agent_id=agent_id,
                            user_context=user_context,
                            conversation_id=effective_conversation_id
                        )
                        all_file_references.append(file_ref)
                        uploaded_file_ids.add(file_ref.file_id)
                        logger.info(f"Uploaded file {upload_file.filename} for agent {agent_id}, conversation {effective_conversation_id}")
                    except Exception as e:
                        logger.error(f"Error uploading file {upload_file.filename}: {str(e)}")
                        # Continue with other files even if one fails
        
        # Get previously uploaded files for this conversation
        existing_files = await file_service.list_attached_files(
            agent_id=agent_id,
            user_context=user_context,
            conversation_id=effective_conversation_id
        )
        
        # Filter existing files if file_references was provided
        if parsed_file_references:
            requested_file_ids = set(parsed_file_references)
            existing_files = [f for f in existing_files if f['file_id'] in requested_file_ids]
            logger.info(f"Filtered to {len(existing_files)} files based on file_references")
        
        # Add existing files (avoiding duplicates from newly uploaded files)
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
        
        if all_file_references:
            logger.info(f"Processing chat with {len(all_file_references)} files for agent {agent_id}")
        
        # Use unified service layer with file references
        execution_service = AgentExecutionService(db)
        result = await execution_service.execute_agent_chat_with_file_refs(
            agent_id=agent_id,
            message=message,
            file_references=all_file_references,
            search_params=parsed_search_params,
            user_context=user_context,
            conversation_id=db_conversation_id,  # Pass the actual DB conversation ID
            db=db
        )
        
        # Build response - always return the effective conversation_id so user can continue the conversation
        response_conversation_id = effective_conversation_id
        if result.get("conversation_id"):
            # Use the conversation_id from the result if available (may differ if auto-created internally)
            response_conversation_id = str(result["conversation_id"])
        
        response_data = AgentResponseSchema(
            response=result["response"],
            conversation_id=response_conversation_id,
            usage=result["metadata"]
        )
        
        logger.debug(f"Chat response prepared for agent {agent_id}, response type: {type(result['response']).__name__}")
        logger.info(f"Public API chat request processed for agent {agent_id} with {len(all_file_references)} files, conversation: {response_conversation_id}")
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in public chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Agent execution failed")


@chat_router.post("/{agent_id}/reset",
                  summary="Reset conversation",
                  tags=["Agent Chat"],
                  response_model=MessageResponseSchema)
async def reset_conversation(
    app_id: int,
    agent_id: int,
    conversation_id: str = None,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """
    Reset the conversation state for an agent.
    
    This will clear the conversation history and any attached files.
    """
    # Validate API key for this app
    auth = validate_api_key_for_app(app_id, api_key)
    
    # Create user context for API key user
    user_context = _create_api_key_user_context(app_id, api_key, conversation_id)
    
    try:
        # Use unified service layer
        execution_service = AgentExecutionService(db)
        success = await execution_service.reset_agent_conversation(
            agent_id=agent_id,
            user_context=user_context,
            db=db
        )
        
        if success:
            logger.info(f"Conversation reset for agent {agent_id} via public API")
            return MessageResponseSchema(message="Conversation reset successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to reset conversation")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in reset conversation endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to reset conversation")
