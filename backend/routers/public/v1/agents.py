from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from services.agent_service import AgentService
from db.database import get_db

from schemas.agent_schemas import (
    PublicAgentSchema,
    PublicAgentDetailSchema,
    PublicAgentsResponseSchema,
    PublicAgentResponseSchema,
    CreateAgentRequestSchema,
    CreateOCRAgentRequestSchema,
    UpdateAgentRequestSchema,
    UpdateOCRAgentRequestSchema
)
from .auth import get_api_key_auth, validate_api_key_for_app

from utils.logger import get_logger

logger = get_logger(__name__)

agents_router = APIRouter()

AGENT_NOT_FOUND = "Agent not found"
OCR_AGENT_NOT_FOUND = "OCR Agent not found"

# ==================== AGENT ENDPOINTS ====================

@agents_router.get("/",
                  summary="List all agents in app",
                  tags=["Agents"],
                  response_model=PublicAgentsResponseSchema)
async def list_agents(
    app_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """List all agents available in the specified app."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    # Use agent service to get agents
    agent_service = AgentService()
    agents = agent_service.get_agents(db, app_id)
    
    # Convert to public schema
    public_agents = [PublicAgentSchema.model_validate(agent) for agent in agents]
    
    return PublicAgentsResponseSchema(agents=public_agents)


@agents_router.get("/{agent_id}",
                  summary="Get agent by ID",
                  tags=["Agents"],
                  response_model=PublicAgentResponseSchema)
async def get_agent(
    app_id: int,
    agent_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """Get a specific agent by ID."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    # Use agent service to get agent
    agent_service = AgentService()
    agent = agent_service.get_agent(db, agent_id)
    
    if not agent or agent.app_id != app_id:
        raise HTTPException(status_code=404, detail=AGENT_NOT_FOUND)
    
    # Convert to public detailed schema
    public_agent = PublicAgentDetailSchema.model_validate(agent)
    
    return PublicAgentResponseSchema(agent=public_agent)


@agents_router.post("/",
                   summary="Create a new agent",
                   tags=["Agents"],
                   response_model=PublicAgentResponseSchema,
                   status_code=status.HTTP_201_CREATED)
async def create_agent(
    app_id: int,
    agent_data: CreateAgentRequestSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """Create a new agent in the specified app."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        # Prepare agent data with app_id
        agent_dict = agent_data.model_dump()
        agent_dict['app_id'] = app_id
        
        # Create agent using service
        agent_service = AgentService()
        agent_id = agent_service.create_or_update_agent(db, agent_dict, 'agent')
        
        # Get the created agent
        created_agent = agent_service.get_agent(db, agent_id)
        public_agent = PublicAgentDetailSchema.model_validate(created_agent)
        
        logger.info(f"Created agent {agent_id} for app {app_id}")
        return PublicAgentResponseSchema(agent=public_agent)
        
    except Exception as e:
        logger.error(f"Error creating agent for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create agent: {str(e)}"
        )


@agents_router.post("/ocr",
                   summary="Create a new OCR agent",
                   tags=["Agents"],
                   response_model=PublicAgentResponseSchema,
                   status_code=status.HTTP_201_CREATED)
async def create_ocr_agent(
    app_id: int,
    agent_data: CreateOCRAgentRequestSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """Create a new OCR agent in the specified app."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        # Prepare agent data with app_id and type
        agent_dict = agent_data.model_dump()
        agent_dict['app_id'] = app_id
        agent_dict['type'] = 'ocr_agent'
        
        # Create OCR agent using service
        agent_service = AgentService()
        agent_id = agent_service.create_or_update_agent(db, agent_dict, 'ocr_agent')
        
        # Get the created agent
        created_agent = agent_service.get_agent(db, agent_id, 'ocr_agent')
        public_agent = PublicAgentDetailSchema.model_validate(created_agent)
        
        logger.info(f"Created OCR agent {agent_id} for app {app_id}")
        return PublicAgentResponseSchema(agent=public_agent)
        
    except Exception as e:
        logger.error(f"Error creating OCR agent for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create OCR agent: {str(e)}"
        )


@agents_router.put("/{agent_id}",
                  summary="Update an existing agent",
                  tags=["Agents"],
                  response_model=PublicAgentResponseSchema)
async def update_agent(
    app_id: int,
    agent_id: int,
    agent_data: UpdateAgentRequestSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """Update an existing agent."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    # Check if agent exists and belongs to the app
    agent_service = AgentService()
    existing_agent = agent_service.get_agent(db, agent_id)
    
    if not existing_agent or existing_agent.app_id != app_id:
        raise HTTPException(status_code=404, detail=AGENT_NOT_FOUND)
    
    try:
        # Prepare update data
        update_dict = agent_data.model_dump(exclude_unset=True)
        update_dict['agent_id'] = agent_id
        update_dict['app_id'] = app_id
        
        # Update agent using service
        updated_agent_id = agent_service.create_or_update_agent(db, update_dict, existing_agent.type)
        
        # Get updated agent
        updated_agent = agent_service.get_agent(db, updated_agent_id)
        public_agent = PublicAgentDetailSchema.model_validate(updated_agent)
        
        logger.info(f"Updated agent {agent_id} for app {app_id}")
        return PublicAgentResponseSchema(agent=public_agent)
        
    except Exception as e:
        logger.error(f"Error updating agent {agent_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update agent: {str(e)}"
        )


@agents_router.put("/ocr/{agent_id}",
                  summary="Update an existing OCR agent",
                  tags=["Agents"],
                  response_model=PublicAgentResponseSchema)
async def update_ocr_agent(
    app_id: int,
    agent_id: int,
    agent_data: UpdateOCRAgentRequestSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """Update an existing OCR agent."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    # Check if OCR agent exists and belongs to the app
    agent_service = AgentService()
    existing_agent = agent_service.get_agent(db, agent_id, 'ocr_agent')
    
    if not existing_agent or existing_agent.app_id != app_id:
        raise HTTPException(status_code=404, detail=OCR_AGENT_NOT_FOUND)
    
    try:
        # Prepare update data
        update_dict = agent_data.model_dump(exclude_unset=True)
        update_dict['agent_id'] = agent_id
        update_dict['app_id'] = app_id
        update_dict['type'] = 'ocr_agent'
        
        # Update OCR agent using service
        updated_agent_id = agent_service.create_or_update_agent(db, update_dict, 'ocr_agent')
        
        # Get updated agent
        updated_agent = agent_service.get_agent(db, updated_agent_id, 'ocr_agent')
        public_agent = PublicAgentDetailSchema.model_validate(updated_agent)
        
        logger.info(f"Updated OCR agent {agent_id} for app {app_id}")
        return PublicAgentResponseSchema(agent=public_agent)
        
    except Exception as e:
        logger.error(f"Error updating OCR agent {agent_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update OCR agent: {str(e)}"
        )


@agents_router.delete("/{agent_id}",
                     summary="Delete an agent",
                     tags=["Agents"],
                     status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    app_id: int,
    agent_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """Delete an agent from the specified app."""
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    # Check if agent exists and belongs to the app
    agent_service = AgentService()
    existing_agent = agent_service.get_agent(db, agent_id)
    
    if not existing_agent or existing_agent.app_id != app_id:
        raise HTTPException(status_code=404, detail=AGENT_NOT_FOUND)
    
    try:
        # Delete agent using service
        success = agent_service.delete_agent(db, agent_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to delete agent"
            )
        
        logger.info(f"Deleted agent {agent_id} from app {app_id}")
        
    except Exception as e:
        logger.error(f"Error deleting agent {agent_id} from app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete agent: {str(e)}"
        ) 