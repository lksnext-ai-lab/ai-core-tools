from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any

# Import services
from services.agent_service import AgentService

# Import schemas and auth
from .schemas import *
from .auth import get_current_user

agents_router = APIRouter()

# ==================== AGENT MANAGEMENT ====================

@agents_router.get("/", 
                  summary="List agents",
                  tags=["Agents"],
                  response_model=List[AgentListItemSchema])
async def list_agents(app_id: int, current_user: dict = Depends(get_current_user)):
    """
    List all agents for a specific app.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    # Get agents using service
    agent_service = AgentService()
    agents = agent_service.get_agents(app_id)
    
    result = []
    for agent in agents:
        result.append(AgentListItemSchema(
            agent_id=agent.agent_id,
            name=agent.name,
            type=agent.type or "agent",
            is_tool=agent.is_tool or False,
            created_at=agent.create_date,
            request_count=agent.request_count or 0
        ))
    
    return result


@agents_router.get("/{agent_id}",
                  summary="Get agent details",
                  tags=["Agents"],
                  response_model=AgentDetailSchema)
async def get_agent(app_id: int, agent_id: int, current_user: dict = Depends(get_current_user)):
    """
    Get detailed information about a specific agent plus form data for editing.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    agent_service = AgentService()
    
    # Get agent details
    if agent_id == 0:
        # New agent
        agent = type('Agent', (), {
            'agent_id': 0, 'name': '', 'system_prompt': '', 'prompt_template': '', 
            'type': 'agent', 'is_tool': False, 'create_date': None, 'request_count': 0
        })()
    else:
        # Existing agent - determine if it's OCR agent or regular agent
        agent = agent_service.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found"
            )
        
        # If it's an OCR agent, get the OCR-specific data
        if agent.type == 'ocr_agent':
            agent = agent_service.get_agent(agent_id, 'ocr')
    
    # Get form data needed for agent configuration - simplified for now
    # TODO: Replace with proper service calls once they're implemented
    from db.session import SessionLocal
    from models.ai_service import AIService
    from models.silo import Silo
    from models.output_parser import OutputParser
    from models.mcp_config import MCPConfig
    
    session = SessionLocal()
    try:
        # Get AI services
        ai_services_query = session.query(AIService).filter(AIService.app_id == app_id).all()
        ai_services = [{"service_id": s.service_id, "name": s.name} for s in ai_services_query]
        
        # Get silos
        silos_query = session.query(Silo).filter(Silo.app_id == app_id).all()
        silos = [{"silo_id": s.silo_id, "name": s.name} for s in silos_query]
        
        # Get output parsers
        parsers_query = session.query(OutputParser).filter(OutputParser.app_id == app_id).all()
        output_parsers = [{"parser_id": p.parser_id, "name": p.name} for p in parsers_query]
        
        # Get tools (agents that are marked as tools)
        tools = agent_service.get_tool_agents(app_id, exclude_agent_id=agent_id)
        tools_list = [{"agent_id": t.agent_id, "name": t.name} for t in tools]
        
        # Get MCP configs
        mcp_query = session.query(MCPConfig).filter(MCPConfig.app_id == app_id).all()
        mcp_configs = [{"config_id": c.config_id, "name": c.name} for c in mcp_query]
        
    finally:
        session.close()
    
    return AgentDetailSchema(
        agent_id=agent.agent_id,
        name=agent.name or "",
        system_prompt=getattr(agent, 'system_prompt', '') or "",
        prompt_template=getattr(agent, 'prompt_template', '') or "",
        type=agent.type or "agent",
        is_tool=agent.is_tool or False,
        created_at=agent.create_date,
        request_count=getattr(agent, 'request_count', 0) or 0,
        # Form data
        ai_services=ai_services,
        silos=silos,
        output_parsers=output_parsers,
        tools=tools_list,
        mcp_configs=mcp_configs
    )


@agents_router.post("/{agent_id}",
                   summary="Create or update agent",
                   tags=["Agents"],
                   response_model=AgentDetailSchema)
async def create_or_update_agent(
    app_id: int,
    agent_id: int,
    agent_data: CreateUpdateAgentSchema,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new agent or update an existing one.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    agent_service = AgentService()
    
    # Prepare agent data
    agent_dict = {
        'agent_id': agent_id,
        'app_id': app_id,
        'name': agent_data.name,
        'system_prompt': agent_data.system_prompt,
        'prompt_template': agent_data.prompt_template,
        'type': agent_data.type,
        'is_tool': agent_data.is_tool
    }
    
    # Create or update agent
    agent = agent_service.create_or_update_agent(agent_dict, agent_data.type)
    
    # Update tools and MCPs if provided
    if agent_data.tool_ids:
        agent_service.update_agent_tools(agent, agent_data.tool_ids, {})
    if agent_data.mcp_config_ids:
        agent_service.update_agent_mcps(agent, agent_data.mcp_config_ids, {})
    
    # Return updated agent (reuse the GET logic)
    return await get_agent(app_id, agent.agent_id, current_user)


@agents_router.delete("/{agent_id}",
                     summary="Delete agent",
                     tags=["Agents"])
async def delete_agent(app_id: int, agent_id: int, current_user: dict = Depends(get_current_user)):
    """
    Delete an agent.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    agent_service = AgentService()
    
    # Check if agent exists
    agent = agent_service.get_agent(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    
    # Delete agent
    success = agent_service.delete_agent(agent_id)
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
    current_user: dict = Depends(get_current_user)
):
    """
    Update agent system prompt or prompt template.
    """
    user_id = current_user["user_id"]
    
    agent_service = AgentService()
    
    # Get agent
    agent = agent_service.get_agent(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    
    # Update the appropriate prompt
    update_data = {'agent_id': agent_id}
    if prompt_data.type == 'system':
        update_data['system_prompt'] = prompt_data.prompt
    elif prompt_data.type == 'template':
        update_data['prompt_template'] = prompt_data.prompt
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid prompt type. Must be 'system' or 'template'"
        )
    
    # Update agent
    agent_service.create_or_update_agent(update_data, agent.type)
    
    return {"message": f"{prompt_data.type.capitalize()} prompt updated successfully"}


# ==================== PLAYGROUND & ANALYTICS ====================

@agents_router.get("/{agent_id}/playground",
                  summary="Get agent playground",
                  tags=["Agents", "Playground"])
async def agent_playground(app_id: int, agent_id: int, current_user: dict = Depends(get_current_user)):
    """
    Get agent playground interface data.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    agent_service = AgentService()
    agent = agent_service.get_agent(agent_id)
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "type": agent.type,
        "playground_url": f"/playground/{agent_id}"  # For frontend routing
    }


@agents_router.get("/{agent_id}/analytics",
                  summary="Get agent analytics",
                  tags=["Agents", "Analytics"])
async def agent_analytics(app_id: int, agent_id: int, current_user: dict = Depends(get_current_user)):
    """
    Get agent analytics data (premium feature).
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    # TODO: Add premium feature check
    
    agent_service = AgentService()
    agent = agent_service.get_agent(agent_id)
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    
    # TODO: Implement actual analytics data collection
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "request_count": agent.request_count or 0,
        "analytics_data": "Analytics feature coming soon"
    } 