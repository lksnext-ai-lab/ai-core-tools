from typing import Union
from app.model.agent import Agent
from app.model.ocr_agent import OCRAgent
from app.extensions import db

class AgentService:
    @staticmethod
    def get_agent(agent_id: int, agent_type: str = 'basic') -> Union[Agent, OCRAgent]:
        if agent_type == 'ocr':
            return db.session.query(OCRAgent).filter(OCRAgent.agent_id == agent_id).first()
        return db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
    
    @staticmethod
    def create_or_update_agent(agent_data: dict, agent_type: str) -> Union[Agent, OCRAgent]:
        agent_id = agent_data.get('agent_id')
        agent = AgentService.get_agent(agent_id, agent_type) if agent_id else None
        
        if not agent:
            agent = OCRAgent() if agent_type == 'ocr_agent' else Agent()
        
        update_method = AgentService._update_ocr_agent if agent_type == 'ocr_agent' else AgentService._update_normal_agent
        update_method(agent, agent_data)
        
        agent.type = agent_type
        db.session.add(agent)
        db.session.commit()
        return agent
    
    @staticmethod
    def _update_ocr_agent(agent: OCRAgent, data: dict):
        was_tool = agent.is_tool
        agent.name = data['name']
        agent.description = data.get('description')
        agent.vision_service_id = data.get('vision_service_id')
        agent.vision_system_prompt = data.get('vision_system_prompt')
        agent.service_id = data.get('service_id')
        agent.text_system_prompt = data.get('text_system_prompt')
        agent.output_parser_id = data.get('output_parser_id') or None
        agent.app_id = data['app_id']
        agent.is_tool = data.get('is_tool') == 'on'
        
        # If agent was a tool but is no longer one, remove all references to it
        if was_tool and not agent.is_tool:
            AgentService._remove_tool_references(agent.agent_id)
    
    @staticmethod
    def _update_normal_agent(agent: Agent, data: dict):
        was_tool = agent.is_tool
        agent.name = data['name']
        agent.description = data.get('description')
        agent.system_prompt = data.get('system_prompt')
        agent.prompt_template = data.get('prompt_template')
        agent.status = data.get('status')
        agent.service_id = data.get('service_id') or None
        agent.host_url = data.get('host_url')
        agent.ollama_model_name = data.get('ollama_model_name')
        agent.app_id = data['app_id']
        agent.silo_id = data.get('silo_id') or None
        agent.has_memory = data.get('has_memory') == 'on'
        agent.output_parser_id = data.get('output_parser_id') or None
        agent.is_tool = data.get('is_tool') == 'on'
        
        # If agent was a tool but is no longer one, remove all references to it
        if was_tool and not agent.is_tool:
            AgentService._remove_tool_references(agent.agent_id)

    @staticmethod
    def update_agent_tools(agent: Agent, tool_ids: list, form_data: dict = None):
        from app.model.agent import AgentTool
        
        # Get existing tool associations
        existing_tools = {assoc.tool_id: assoc for assoc in agent.tool_associations}
        
        # Convert tool_ids to set of integers and filter out non-tool agents
        tools_query = db.session.query(Agent.agent_id).filter(
            Agent.agent_id.in_([int(id) for id in tool_ids if id]),
            Agent.is_tool == True
        )
        valid_tool_ids = {id for (id,) in tools_query}
        
        # Remove associations that are no longer needed
        for tool_id in list(existing_tools.keys()):
            if tool_id not in valid_tool_ids:
                db.session.delete(existing_tools[tool_id])
        
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
        
        db.session.commit()
    
    @staticmethod
    def delete_agent(agent_id: int):
        agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
        if agent:
            # First remove all references to this agent as a tool
            AgentService._remove_tool_references(agent_id)
            # Then delete the agent
            db.session.delete(agent)
            db.session.commit()

    @staticmethod
    def _remove_tool_references(tool_id: int):
        """Remove all references to an agent as a tool from other agents."""
        from app.model.agent import AgentTool
        # Delete all tool associations where this agent is used as a tool
        db.session.query(AgentTool).filter(AgentTool.tool_id == tool_id).delete()
        db.session.commit()
