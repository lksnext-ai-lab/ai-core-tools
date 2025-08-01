from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
import json
import tempfile
import os

# Import our services
from services.agent_service import AgentService
from services.silo_service import SiloService
from services.repository_service import RepositoryService
from services.resource_service import ResourceService

# Import Pydantic models and auth
from .schemas import *
from .auth import get_api_key_auth, validate_api_key_for_app, APIKeyAuth

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

chat_router = APIRouter()

# ==================== AGENT CHAT ENDPOINTS ====================

@chat_router.post("/{agent_id}/call", 
                  summary="Call agent", 
                  tags=["Agent Chat"],
                  response_model=AgentResponseSchema)
async def call_agent(
    app_id: int,
    agent_id: int,
    request: ChatRequestSchema,
    api_key: str = Depends(get_api_key_auth)
):
    """
    Call an agent for chat completion.
    Supports both text and file attachments.
    """
    # Validate API key for this app
    auth = validate_api_key_for_app(app_id, api_key)
    
    # Create user context for API key user
    user_context = {
        "api_key": api_key,
        "app_id": app_id,
        "oauth": False
    }
    
    # Use unified service layer
    from services.agent_execution_service import AgentExecutionService
    execution_service = AgentExecutionService()
    
    try:
        result = await execution_service.execute_agent_chat(
            agent_id=agent_id,
            message=request.message,
            files=None,  # TODO: Handle file attachments from request
            search_params=request.search_params,
            user_context=user_context
        )
        
        return AgentResponseSchema(
            response=result["response"],
            conversation_id=f"api_{agent_id}_{api_key[:8]}",
            usage=result["metadata"]
        )
        
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
    api_key: str = Depends(get_api_key_auth)
):
    """Reset the conversation state for an agent."""
    # Validate API key for this app
    auth = validate_api_key_for_app(app_id, api_key)
    
    # Create user context for API key user
    user_context = {
        "api_key": api_key,
        "app_id": app_id,
        "oauth": False
    }
    
    # Use unified service layer
    from services.agent_execution_service import AgentExecutionService
    execution_service = AgentExecutionService()
    
    try:
        success = await execution_service.reset_agent_conversation(
            agent_id=agent_id,
            user_context=user_context
        )
        
        if success:
            return MessageResponseSchema(message="Conversation reset successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to reset conversation")
            
    except Exception as e:
        logger.error(f"Error in reset conversation endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to reset conversation") 