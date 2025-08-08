from typing import Union
from models.agent import Agent, AgentMCP
from models.ocr_agent import OCRAgent
from db.database import SessionLocal

class AgentService:

    def get_agents(self, app_id: int) -> list[Agent]:
        session = SessionLocal()
        try:
            return session.query(Agent).filter(Agent.app_id == app_id).order_by(Agent.create_date.desc()).all()
        finally:
            session.close()

    def get_tool_agents(self, app_id: int, exclude_agent_id: int = None) -> list[Agent]:
        """Get agents that are marked as tools"""
        session = SessionLocal()
        try:
            query = session.query(Agent).filter(
                Agent.app_id == app_id,
                Agent.is_tool == True
            )
            if exclude_agent_id:
                query = query.filter(Agent.agent_id != exclude_agent_id)
            
            return query.all()
        finally:
            session.close()

    @staticmethod
    def get_agent(agent_id: int, agent_type: str = 'basic') -> Union[Agent, OCRAgent]:
        session = SessionLocal()
        try:
            if agent_type == 'ocr' or agent_type == 'ocr_agent':
                return session.query(OCRAgent).filter(OCRAgent.agent_id == agent_id).first()
            elif agent_type == 'basic' or agent_type == 'agent':
                return session.query(Agent).filter(Agent.agent_id == agent_id).first()
            else:
                # Try both tables
                agent = session.query(Agent).filter(Agent.agent_id == agent_id).first()
                if not agent:
                    agent = session.query(OCRAgent).filter(OCRAgent.agent_id == agent_id).first()
                return agent
        finally:
            session.close()
    
    @staticmethod
    def create_or_update_agent(agent_data: dict, agent_type: str) -> int:
        session = SessionLocal()
        try:
            agent_id = agent_data.get('agent_id')
            agent = AgentService.get_agent(agent_id, agent_type) if agent_id else None
            
            if not agent:
                agent = Agent()
            
            update_method = AgentService._update_normal_agent
            update_method(agent, agent_data)
            
            agent.type = agent_type
            session.add(agent)
            session.commit()
            
            # Return the agent ID before closing the session
            return agent.agent_id
        finally:
            session.close()


    
    @staticmethod
    def _update_normal_agent(agent: Agent, data: dict):
        was_tool = agent.is_tool
        agent.name = data['name']
        agent.description = data.get('description', '')  # Ensure it's not None
        agent.system_prompt = data.get('system_prompt')
        agent.prompt_template = data.get('prompt_template')
        agent.status = data.get('status')
        agent.service_id = data.get('service_id') or None
        agent.host_url = data.get('host_url')
        agent.ollama_model_name = data.get('ollama_model_name')
        agent.app_id = data['app_id']
        agent.silo_id = data.get('silo_id') or None
        # Handle has_memory field - can be boolean from API or 'on' from form
        has_memory_value = data.get('has_memory')
        if isinstance(has_memory_value, bool):
            agent.has_memory = has_memory_value
        else:
            agent.has_memory = has_memory_value == 'on'
        agent.output_parser_id = data.get('output_parser_id') or None
        
        # OCR-specific fields
        agent.vision_service_id = data.get('vision_service_id')
        agent.vision_system_prompt = data.get('vision_system_prompt')
        agent.text_system_prompt = data.get('text_system_prompt')
        
        # Handle is_tool field - can be boolean from API or 'on' from form
        is_tool_value = data.get('is_tool')
        if isinstance(is_tool_value, bool):
            agent.is_tool = is_tool_value
        else:
            agent.is_tool = is_tool_value == 'on'
        
        # If agent was a tool but is no longer one, remove all references to it
        if was_tool and not agent.is_tool:
            AgentService._remove_tool_references(agent.agent_id)

    @staticmethod
    def update_agent_tools(agent_id: int, tool_ids: list, form_data: dict = None):
        from models.agent import AgentTool
        session = SessionLocal()
        try:
            # Get the agent with associations
            agent = session.query(Agent).filter(Agent.agent_id == agent_id).first()
            if not agent:
                return
            
            # Get existing tool associations
            existing_tools = {assoc.tool_id: assoc for assoc in agent.tool_associations}
            
            # Convert tool_ids to set of integers and filter out non-tool agents
            tools_query = session.query(Agent.agent_id).filter(
                Agent.agent_id.in_([int(id) for id in tool_ids if id]),
                Agent.is_tool == True
            )
            valid_tool_ids = {id for (id,) in tools_query}
            
            # Remove associations that are no longer needed
            for tool_id in list(existing_tools.keys()):
                if tool_id not in valid_tool_ids:
                    session.delete(existing_tools[tool_id])
            
            # Update or create associations
            for tool_id in valid_tool_ids:
                description = form_data.get(f'tool_description_{tool_id}') if form_data else None
                
                if tool_id in existing_tools:
                    # Update existing association
                    existing_tools[tool_id].description = description
                else:
                    # Create new association
                    tool_assoc = AgentTool(
                        agent_id=agent.agent_id,
                        tool_id=tool_id,
                        description=description
                    )
                    agent.tool_associations.append(tool_assoc)
            
            session.commit()
        finally:
            session.close()
    
    @staticmethod
    def update_agent_mcps(agent_id: int, mcp_ids: list, form_data: dict = None):
        from models.agent import AgentMCP
        session = SessionLocal()
        try:
            # Get the agent with associations
            agent = session.query(Agent).filter(Agent.agent_id == agent_id).first()
            if not agent:
                return
            
            # Convert mcp_ids to list if it's not already
            if isinstance(mcp_ids, str):
                mcp_ids = [mcp_ids]
            elif not isinstance(mcp_ids, list):
                mcp_ids = []

            # Get existing MCP associations
            existing_mcps = {assoc.config_id: assoc for assoc in agent.mcp_associations}
            
            # Convert mcp_ids to set of integers
            valid_mcp_ids = {int(id) for id in mcp_ids if id}
            
            # Remove associations that are no longer needed
            for mcp_id in list(existing_mcps.keys()):
                if mcp_id not in valid_mcp_ids:
                    session.delete(existing_mcps[mcp_id])
            
            # Update or create associations
            for mcp_id in valid_mcp_ids:
                description = form_data.get(f'mcp_description_{mcp_id}') if form_data else None
                
                if mcp_id in existing_mcps:
                    # Update existing association
                    existing_mcps[mcp_id].description = description
                else:
                    # Create new association
                    mcp_assoc = AgentMCP(
                        agent_id=agent.agent_id,
                        config_id=mcp_id,
                        description=description
                    )
                    agent.mcp_associations.append(mcp_assoc)
            
            session.commit()
        finally:
            session.close()
    
    @staticmethod
    def delete_agent(agent_id: int):
        session = SessionLocal()
        try:
            # Check both Agent and OCRAgent tables
            agent = session.query(Agent).filter(Agent.agent_id == agent_id).first()
            if not agent:
                agent = session.query(OCRAgent).filter(OCRAgent.agent_id == agent_id).first()
            
            if agent:
                # First remove all references to this agent as a tool
                AgentService._remove_tool_references(agent_id)
                # Then delete the agent
                session.delete(agent)
                session.commit()
                return True
            return False
        finally:
            session.close()

    @staticmethod
    def _remove_tool_references(tool_id: int):
        from models.agent import AgentTool
        session = SessionLocal()
        try:
            # Delete all tool associations where this agent is used as a tool
            session.query(AgentTool).filter(AgentTool.tool_id == tool_id).delete()
            session.commit()
        finally:
            session.close() 