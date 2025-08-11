from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List
from sqlalchemy.orm import Session

from services.agent_service import AgentService
from db.database import get_db
from schemas.agent_schemas import AgentListItemSchema, AgentDetailSchema, CreateUpdateAgentSchema, UpdatePromptSchema
from routers.internal.auth_utils import get_current_user_oauth

from utils.logger import get_logger

logger = get_logger(__name__)

agents_router = APIRouter()

# ==================== CONSTANTS ====================

AGENT_NOT_FOUND_ERROR = "Agent not found"

# ==================== DEPENDENCIES ====================

def get_agent_service() -> AgentService:
    """Dependency to get AgentService instance"""
    return AgentService()

# ==================== AGENT MANAGEMENT ====================

@agents_router.get("/", 
                  summary="List agents",
                  tags=["Agents"],
                  response_model=List[AgentListItemSchema])
async def list_agents(
    app_id: int, 
    current_user: dict = Depends(get_current_user_oauth),
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
    current_user: dict = Depends(get_current_user_oauth),
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
    current_user: dict = Depends(get_current_user_oauth),
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
    return await get_agent(app_id, created_agent_id, current_user, db, agent_service)


@agents_router.delete("/{agent_id}",
                     summary="Delete agent",
                     tags=["Agents"])
async def delete_agent(
    app_id: int, 
    agent_id: int, 
    current_user: dict = Depends(get_current_user_oauth),
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
    agent_id: int,
    prompt_data: UpdatePromptSchema,
    current_user: dict = Depends(get_current_user_oauth),
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
    current_user: dict = Depends(get_current_user_oauth),
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
    current_user: dict = Depends(get_current_user_oauth),
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