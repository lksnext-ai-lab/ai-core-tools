from fastapi import APIRouter, Depends, HTTPException
from typing import List

# Import services
from services.agent_service import AgentService

# Import schemas and auth
from .schemas import AgentSchema, AgentsResponseSchema
from .auth import get_api_key_auth, validate_api_key_for_app

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

agents_router = APIRouter()

# ==================== AGENT ENDPOINTS ====================

@agents_router.get("/",
                  summary="List all agents in app",
                  tags=["Agents"],
                  response_model=AgentsResponseSchema)
async def list_agents(
    app_id: int,
    api_key: str = Depends(get_api_key_auth)
):
    """List all agents available in the specified app."""
    # Validate API key for this app
    auth = validate_api_key_for_app(app_id, api_key)
    
    # Use agent service to get agents
    agent_service = AgentService()
    agents = agent_service.get_agents(app_id)
    
    return AgentsResponseSchema(agents=agents)


@agents_router.get("/{agent_id}",
                  summary="Get agent by ID",
                  tags=["Agents"],
                  response_model=AgentSchema)
async def get_agent(
    app_id: int,
    agent_id: int,
    api_key: str = Depends(get_api_key_auth)
):
    """Get a specific agent by ID."""
    # Validate API key for this app
    auth = validate_api_key_for_app(app_id, api_key)
    
    # Use agent service to get agent
    agent_service = AgentService()
    agent = agent_service.get_agent(agent_id)
    
    if not agent or agent.app_id != app_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return agent 