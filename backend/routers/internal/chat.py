import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import List, Optional
from pydantic import BaseModel

from routers.internal.auth_utils import get_current_user_oauth
from services.agent_execution_service import AgentExecutionService
from services.file_management_service import FileManagementService
from utils.logger import get_logger

logger = get_logger(__name__)

chat_router = APIRouter(tags=["Internal Chat"])


async def _save_uploaded_file(upload_file: UploadFile) -> str:
    """Save uploaded file to temporary location and return file path"""
    import tempfile
    import os
    
    # Create temporary file
    suffix = os.path.splitext(upload_file.filename)[1] if upload_file.filename else ''
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        content = await upload_file.read()
        temp_file.write(content)
        temp_file_path = temp_file.name
    
    return temp_file_path


class ChatRequestSchema(BaseModel):
    """Schema for chat request"""
    message: str
    files: Optional[List[str]] = None  # File IDs
    search_params: Optional[dict] = None


from typing import Union

class ChatResponseSchema(BaseModel):
    """Schema for chat response"""
    response: Union[str, dict]  # Can be string or JSON object
    agent_id: int
    metadata: dict


class ResetResponseSchema(BaseModel):
    """Schema for reset response"""
    success: bool
    message: str


@chat_router.post("/{agent_id}/chat",
                  summary="Chat with agent",
                  tags=["Internal Chat"],
                  response_model=ChatResponseSchema)
async def chat_with_agent(
    agent_id: int,
    message: str = Form(...),
    files: List[UploadFile] = File(None),
    search_params: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Internal API: Chat with agent for playground (OAuth authentication)
    """
    try:
        # Parse search params if provided
        parsed_search_params = None
        if search_params:
            try:
                parsed_search_params = json.loads(search_params)
            except json.JSONDecodeError:
                logger.warning(f"Invalid search_params JSON: {search_params}")
        
        # Create user context for OAuth user
        user_context = {
            "user_id": current_user["user_id"],
            "oauth": True,
            "app_id": current_user.get("app_id")
        }
        
        # Convert UploadFile objects to File objects for the service
        file_objects = []
        if files:
            for upload_file in files:
                # Save the uploaded file temporarily
                temp_file = await _save_uploaded_file(upload_file)
                file_objects.append(temp_file)
        
        # Use unified service layer
        execution_service = AgentExecutionService()
        result = await execution_service.execute_agent_chat(
            agent_id=agent_id,
            message=message,
            files=file_objects if file_objects else None,
            search_params=parsed_search_params,
            user_context=user_context
        )
        
        logger.info(f"Chat request processed for agent {agent_id} by user {current_user['user_id']}")
        return ChatResponseSchema(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@chat_router.post("/{agent_id}/reset",
                  summary="Reset conversation",
                  tags=["Internal Chat"],
                  response_model=ResetResponseSchema)
async def reset_conversation(
    agent_id: int,
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Internal API: Reset conversation for playground (OAuth authentication)
    """
    try:
        # Create user context for OAuth user
        user_context = {
            "user_id": current_user["user_id"],
            "oauth": True,
            "app_id": current_user.get("app_id")
        }
        
        # Use unified service layer
        execution_service = AgentExecutionService()
        success = await execution_service.reset_agent_conversation(
            agent_id=agent_id,
            user_context=user_context
        )
        
        if success:
            logger.info(f"Conversation reset for agent {agent_id} by user {current_user['user_id']}")
            return ResetResponseSchema(success=True, message="Conversation reset successfully")
        else:
            return ResetResponseSchema(success=False, message="Failed to reset conversation")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in reset endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@chat_router.post("/{agent_id}/upload-file",
                  summary="Upload file for chat",
                  tags=["Internal Chat"])
async def upload_file_for_chat(
    agent_id: int,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Internal API: Upload file for chat (OAuth authentication)
    """
    try:
        # Create user context for OAuth user
        user_context = {
            "user_id": current_user["user_id"],
            "oauth": True,
            "app_id": current_user.get("app_id")
        }
        
        # Use unified service layer
        file_service = FileManagementService()
        file_ref = await file_service.upload_file(
            file=file,
            agent_id=agent_id,
            user_context=user_context
        )
        
        logger.info(f"File uploaded for agent {agent_id} by user {current_user['user_id']}")
        return {
            "success": True,
            "file_id": file_ref.file_id,
            "filename": file_ref.filename,
            "file_type": file_ref.file_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in file upload endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="File upload failed")


@chat_router.get("/{agent_id}/files",
                 summary="List attached files",
                 tags=["Internal Chat"])
async def list_attached_files(
    agent_id: int,
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Internal API: List attached files for chat (OAuth authentication)
    """
    try:
        # Create user context for OAuth user
        user_context = {
            "user_id": current_user["user_id"],
            "oauth": True,
            "app_id": current_user.get("app_id")
        }
        
        # Use unified service layer
        file_service = FileManagementService()
        files = await file_service.list_attached_files(
            agent_id=agent_id,
            user_context=user_context
        )
        
        return {"files": files}
        
    except Exception as e:
        logger.error(f"Error in list files endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list files")


@chat_router.delete("/{agent_id}/files/{file_id}",
                    summary="Remove attached file",
                    tags=["Internal Chat"])
async def remove_attached_file(
    agent_id: int,
    file_id: str,
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Internal API: Remove attached file (OAuth authentication)
    """
    try:
        # Create user context for OAuth user
        user_context = {
            "user_id": current_user["user_id"],
            "oauth": True,
            "app_id": current_user.get("app_id")
        }
        
        # Use unified service layer
        file_service = FileManagementService()
        success = await file_service.remove_file(
            file_id=file_id,
            user_context=user_context
        )
        
        if success:
            logger.info(f"File {file_id} removed for agent {agent_id} by user {current_user['user_id']}")
            return {"success": True, "message": "File removed successfully"}
        else:
            return {"success": False, "message": "File not found or already removed"}
            
    except Exception as e:
        logger.error(f"Error in remove file endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to remove file") 