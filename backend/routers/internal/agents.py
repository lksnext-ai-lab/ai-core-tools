from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List

from services.agent_service import AgentService

from .schemas import *
from routers.auth import verify_jwt_token

from utils.logger import get_logger

logger = get_logger(__name__)

agents_router = APIRouter()

# ==================== AUTHENTICATION ====================

async def get_current_user_oauth(request: Request):
    """
    Get current authenticated user using Google OAuth JWT tokens.
    Compatible with the frontend auth system.
    """
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        logger.info(f"Auth header received: {auth_header[:20] + '...' if auth_header and len(auth_header) > 20 else auth_header}")
        
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.error("No Authorization header or invalid format")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please provide Authorization header with Bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = auth_header.split(' ')[1]
        logger.info(f"Token extracted: {token[:20] + '...' if len(token) > 20 else token}")
        
        # Verify token using Google OAuth system
        payload = verify_jwt_token(token)
        if not payload:
            logger.error("Token verification failed - invalid or expired token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.info(f"Token verified successfully for user: {payload.get('user_id')}")
        return payload
        
    except HTTPException:
        logger.error("HTTPException in authentication, re-raising")
        raise
    except Exception as e:
        logger.error(f"Error in authentication: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

# ==================== AGENT MANAGEMENT ====================

@agents_router.get("/", 
                  summary="List agents",
                  tags=["Agents"],
                  response_model=List[AgentListItemSchema])
async def list_agents(app_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    List all agents for a specific app.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    # Get agents using service
    agent_service = AgentService()
    agents = agent_service.get_agents(app_id)
    
    # Get AI services for this app to include in response
    from db.database import SessionLocal
    from models.ai_service import AIService
    
    session = SessionLocal()
    try:
        ai_services_query = session.query(AIService).filter(AIService.app_id == app_id).all()
        ai_services_dict = {s.service_id: {"name": s.name, "model_name": s.description, "provider": s.provider} for s in ai_services_query}
    finally:
        session.close()
    
    result = []
    for agent in agents:
        # Get AI service details if agent has one
        ai_service_info = None
        if hasattr(agent, 'service_id') and agent.service_id and agent.service_id in ai_services_dict:
            ai_service_info = ai_services_dict[agent.service_id]
        
        result.append(AgentListItemSchema(
            agent_id=agent.agent_id,
            name=agent.name,
            type=agent.type or "agent",
            is_tool=agent.is_tool or False,
            created_at=agent.create_date,
            request_count=agent.request_count or 0,
            service_id=getattr(agent, 'service_id', None),
            ai_service=ai_service_info
        ))
    
    return result


@agents_router.get("/{agent_id}",
                  summary="Get agent details",
                  tags=["Agents"],
                  response_model=AgentDetailSchema)
async def get_agent(app_id: int, agent_id: int, current_user: dict = Depends(get_current_user_oauth)):
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
    from db.database import SessionLocal
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
        
        # Get agent's current associations
        agent_tool_ids = []
        agent_mcp_ids = []
        
        # Get silo information for playground
        silo_info = None
        if agent_id != 0:
            # Get tool associations
            from models.agent import AgentTool
            tool_assocs = session.query(AgentTool).filter(AgentTool.agent_id == agent_id).all()
            agent_tool_ids = [assoc.tool_id for assoc in tool_assocs]
            
            # Get MCP associations
            from models.agent import AgentMCP
            mcp_assocs = session.query(AgentMCP).filter(AgentMCP.agent_id == agent_id).all()
            agent_mcp_ids = [assoc.config_id for assoc in mcp_assocs]
            
            # Get silo information if agent has a silo
            if hasattr(agent, 'silo_id') and agent.silo_id:
                silo = session.query(Silo).filter(Silo.silo_id == agent.silo_id).first()
                if silo:
                    silo_info = {
                        "silo_id": silo.silo_id,
                        "name": silo.name,
                        "metadata_definition": None
                    }
                    
                    # Get metadata definition if it exists
                    if silo.metadata_definition_id:
                        from models.output_parser import OutputParser
                        metadata_parser = session.query(OutputParser).filter(OutputParser.parser_id == silo.metadata_definition_id).first()
                        if metadata_parser and metadata_parser.fields:
                            silo_info["metadata_definition"] = {
                                "fields": metadata_parser.fields if metadata_parser.fields else []
                            }
        
        # Get output parser information if agent has one
        output_parser_info = None
        if hasattr(agent, 'output_parser_id') and agent.output_parser_id:
            output_parser = session.query(OutputParser).filter(OutputParser.parser_id == agent.output_parser_id).first()
            if output_parser:
                output_parser_info = {
                    "parser_id": output_parser.parser_id,
                    "name": output_parser.name,
                    "description": output_parser.description,
                    "fields": output_parser.fields if output_parser.fields else []
                }
        
    finally:
        session.close()
    
    return AgentDetailSchema(
        agent_id=agent.agent_id,
        name=agent.name or "",
        description=getattr(agent, 'description', '') or "",
        system_prompt=getattr(agent, 'system_prompt', '') or "",
        prompt_template=getattr(agent, 'prompt_template', '') or "",
        type=agent.type or "agent",
        is_tool=agent.is_tool or False,
        has_memory=getattr(agent, 'has_memory', False) or False,
        service_id=getattr(agent, 'service_id', None),
        silo_id=getattr(agent, 'silo_id', None),
        output_parser_id=getattr(agent, 'output_parser_id', None),
        tool_ids=agent_tool_ids,
        mcp_config_ids=agent_mcp_ids,
        created_at=agent.create_date,
        request_count=getattr(agent, 'request_count', 0) or 0,
        # OCR-specific fields
        vision_service_id=getattr(agent, 'vision_service_id', None),
        vision_system_prompt=getattr(agent, 'vision_system_prompt', None),
        text_system_prompt=getattr(agent, 'text_system_prompt', None),
        # Silo information for playground
        silo=silo_info,
        # Output parser information for playground
        output_parser=output_parser_info,
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
    current_user: dict = Depends(get_current_user_oauth)
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
    created_agent_id = agent_service.create_or_update_agent(agent_dict, agent_data.type)
    
    # Update tools and MCPs (always call to handle empty arrays for unselecting)
    agent_service.update_agent_tools(created_agent_id, agent_data.tool_ids, {})
    agent_service.update_agent_mcps(created_agent_id, agent_data.mcp_config_ids, {})
    
    # Return updated agent (reuse the GET logic)
    return await get_agent(app_id, created_agent_id, current_user)


@agents_router.delete("/{agent_id}",
                     summary="Delete agent",
                     tags=["Agents"])
async def delete_agent(app_id: int, agent_id: int, current_user: dict = Depends(get_current_user_oauth)):
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
    current_user: dict = Depends(get_current_user_oauth)
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
async def agent_playground(app_id: int, agent_id: int, current_user: dict = Depends(get_current_user_oauth)):
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
async def agent_analytics(app_id: int, agent_id: int, current_user: dict = Depends(get_current_user_oauth)):
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