from typing import Union, List, Dict, Any, Optional
from sqlalchemy.orm import Session
from models.agent import Agent
from models.ocr_agent import OCRAgent
from schemas.agent_schemas import AgentListItemSchema, AgentDetailSchema
from repositories.agent_repository import AgentRepository

class AgentService:

    def get_agents_list(self, db: Session, app_id: int) -> List[AgentListItemSchema]:
        """Get list of agents with AI service details for display"""
        agents = AgentRepository.get_by_app_id(db, app_id)
        
        # Get AI services for this app
        ai_services_dict = AgentRepository.get_ai_services_dict_by_app_id(db, app_id)
        
        result = []
        for agent in agents:
            # Get AI service details if agent has one
            ai_service_info = None
            if hasattr(agent, 'service_id') and agent.service_id and agent.service_id in ai_services_dict:
                ai_service_info = ai_services_dict[agent.service_id]
            
            result.append(AgentListItemSchema(
                agent_id=agent.agent_id,
                name=agent.name,
                description=getattr(agent, 'description', None),
                type=agent.type or "agent",
                is_tool=agent.is_tool or False,
                created_at=agent.create_date,
                request_count=agent.request_count or 0,
                service_id=getattr(agent, 'service_id', None),
                ai_service=ai_service_info
            ))
        
        return result

    def get_agents(self, db: Session, app_id: int) -> List[Agent]:
        """Get raw agent objects"""
        return AgentRepository.get_by_app_id(db, app_id)

    def get_tool_agents(self, db: Session, app_id: int, exclude_agent_id: int = None) -> List[Agent]:
        """Get agents that are marked as tools"""
        return AgentRepository.get_tool_agents_by_app_id(db, app_id, exclude_agent_id)

    def get_agent_detail(self, db: Session, app_id: int, agent_id: int) -> Optional[AgentDetailSchema]:
        """Get detailed agent information with form data for editing"""
        
        # Get agent details
        agent = self._get_agent_for_detail(db, agent_id)
        if agent_id != 0 and not agent:
            return None
        
        # Get form data for dropdowns
        form_data = self._get_form_data(db, app_id, agent_id)
        
        # Get agent associations
        associations = self._get_agent_associations(db, agent_id)
        
        # Get related information
        silo_info = self._get_silo_info(db, agent) if agent_id != 0 else None
        output_parser_info = self._get_output_parser_info(db, agent) if agent_id != 0 else None
        
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
            tool_ids=associations['tool_ids'],
            mcp_config_ids=associations['mcp_ids'],
            created_at=agent.create_date,
            request_count=getattr(agent, 'request_count', 0) or 0,
            # OCR-specific fields
            vision_service_id=getattr(agent, 'vision_service_id', None),
            vision_system_prompt=getattr(agent, 'vision_system_prompt', None),
            text_system_prompt=getattr(agent, 'text_system_prompt', None),
            # Related information
            silo=silo_info,
            output_parser=output_parser_info,
            # Form data
            ai_services=form_data['ai_services'],
            silos=form_data['silos'],
            output_parsers=form_data['output_parsers'],
            tools=form_data['tools'],
            mcp_configs=form_data['mcp_configs']
        )

    def _get_agent_for_detail(self, db: Session, agent_id: int):
        """Get agent for detail view"""
        if agent_id == 0:
            # New agent
            return type('Agent', (), {
                'agent_id': 0, 'name': '', 'system_prompt': '', 'prompt_template': '', 
                'type': 'agent', 'is_tool': False, 'create_date': None, 'request_count': 0
            })()
        else:
            # Existing agent - determine if it's OCR agent or regular agent
            agent = self.get_agent(db, agent_id)
            if not agent:
                return None
            
            # If it's an OCR agent, get the OCR-specific data
            if agent.type == 'ocr_agent':
                agent = self.get_agent(db, agent_id, 'ocr')
            return agent

    def _get_form_data(self, db: Session, app_id: int, agent_id: int) -> Dict[str, List]:
        """Get form data for dropdowns"""
        return AgentRepository.get_form_data_for_agent(db, app_id, agent_id)

    def _get_agent_associations(self, db: Session, agent_id: int) -> Dict[str, List]:
        """Get agent's current associations"""
        return AgentRepository.get_agent_associations_dict(db, agent_id)

    def _get_silo_info(self, db: Session, agent) -> Optional[Dict[str, Any]]:
        """Get silo information if agent has one"""
        if not hasattr(agent, 'silo_id') or not agent.silo_id:
            return None
        
        return AgentRepository.get_silo_with_metadata_definition(db, agent.silo_id)

    def _get_output_parser_info(self, db: Session, agent) -> Optional[Dict[str, Any]]:
        """Get output parser information if agent has one"""
        if not hasattr(agent, 'output_parser_id') or not agent.output_parser_id:
            return None
        
        return AgentRepository.get_output_parser_info(db, agent.output_parser_id)

    def get_agent(self, db: Session, agent_id: int, agent_type: str = 'basic') -> Union[Agent, OCRAgent]:
        """Get agent by ID and type"""
        return AgentRepository.get_agent_by_id_and_type(db, agent_id, agent_type)
    
    def create_or_update_agent(self, db: Session, agent_data: dict, agent_type: str) -> int:
        """Create or update agent"""
        agent_id = agent_data.get('agent_id')
        agent = AgentRepository.get_agent_by_id_and_type(db, agent_id, agent_type) if agent_id else None
        
        if not agent:
            agent = Agent()
        
        update_method = self._update_normal_agent
        update_method(agent, agent_data)
        
        agent.type = agent_type
        
        # Use repository to save the agent
        if agent.agent_id:
            agent = AgentRepository.update(db, agent)
        else:
            agent = AgentRepository.create(db, agent)
        
        # Return the agent ID
        return agent.agent_id


    
    def _update_normal_agent(self, agent: Agent, data: dict):
        """Update agent fields"""
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

    def update_agent_tools(self, db: Session, agent_id: int, tool_ids: list, form_data: dict = None):
        """Update agent tools associations"""
        # Get the agent
        agent = AgentRepository.get_by_id(db, agent_id)
        if not agent:
            return
        
        # Get existing tool associations
        existing_tools = {assoc.tool_id: assoc for assoc in AgentRepository.get_agent_tool_associations(db, agent_id)}
        
        # Convert tool_ids to set of integers and filter out non-tool agents
        valid_tool_ids = set(AgentRepository.get_valid_tool_ids(db, [int(id) for id in tool_ids if id]))
        
        # Remove associations that are no longer needed
        for tool_id in existing_tools.keys():
            if tool_id not in valid_tool_ids:
                AgentRepository.delete_agent_tool_association(db, existing_tools[tool_id])
        
        # Update or create associations
        for tool_id in valid_tool_ids:
            description = form_data.get(f'tool_description_{tool_id}') if form_data else None
            
            if tool_id in existing_tools:
                # Update existing association
                existing_tools[tool_id].description = description
                db.add(existing_tools[tool_id])
            else:
                # Create new association
                AgentRepository.create_agent_tool_association(db, agent_id, tool_id, description)
        
        db.commit()
    
    def update_agent_mcps(self, db: Session, agent_id: int, mcp_ids: list, form_data: dict = None):
        """Update agent MCP associations"""
        # Get the agent
        agent = AgentRepository.get_by_id(db, agent_id)
        if not agent:
            return
        
        # Convert mcp_ids to list if it's not already
        if isinstance(mcp_ids, str):
            mcp_ids = [mcp_ids]
        elif not isinstance(mcp_ids, list):
            mcp_ids = []

        # Get existing MCP associations
        existing_mcps = {assoc.config_id: assoc for assoc in AgentRepository.get_agent_mcp_associations(db, agent_id)}
        
        # Convert mcp_ids to set of integers
        valid_mcp_ids = {int(id) for id in mcp_ids if id}
        
        # Remove associations that are no longer needed
        for mcp_id in existing_mcps.keys():
            if mcp_id not in valid_mcp_ids:
                AgentRepository.delete_agent_mcp_association(db, existing_mcps[mcp_id])
        
        # Update or create associations
        for mcp_id in valid_mcp_ids:
            description = form_data.get(f'mcp_description_{mcp_id}') if form_data else None
            
            if mcp_id in existing_mcps:
                # Update existing association
                existing_mcps[mcp_id].description = description
                db.add(existing_mcps[mcp_id])
            else:
                # Create new association
                AgentRepository.create_agent_mcp_association(db, agent_id, mcp_id, description)
        
        db.commit()
    
    def delete_agent(self, db: Session, agent_id: int) -> bool:
        """Delete agent"""
        return AgentRepository.delete_by_id(db, agent_id)

    def _remove_tool_references(self, db: Session, tool_id: int):
        """Remove all tool associations where this agent is used as a tool"""
        AgentRepository.remove_tool_references(db, tool_id)

    def update_agent_prompt(self, db: Session, agent_id: int, prompt_type: str, prompt: str) -> bool:
        """Update agent prompt (system or template)"""
        agent = AgentRepository.get_agent_by_id_and_type(db, agent_id)
        if not agent:
            return False
        
        # Update the appropriate prompt
        update_data = {'agent_id': agent_id}
        if prompt_type == 'system':
            update_data['system_prompt'] = prompt
        elif prompt_type == 'template':
            update_data['prompt_template'] = prompt
        else:
            return False
        
        # Update agent
        self.create_or_update_agent(db, update_data, agent.type)
        return True

    def get_agent_playground_data(self, db: Session, agent_id: int) -> Optional[Dict[str, Any]]:
        """Get agent playground data"""
        agent = AgentRepository.get_agent_by_id_and_type(db, agent_id)
        if not agent:
            return None
        
        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "type": agent.type,
            "playground_url": f"/playground/{agent_id}"
        }

    def get_agent_analytics(self, db: Session, agent_id: int) -> Optional[Dict[str, Any]]:
        """Get agent analytics data"""
        agent = AgentRepository.get_agent_by_id_and_type(db, agent_id)
        if not agent:
            return None
        
        # Return analytics data with actual implementation placeholder
        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "request_count": agent.request_count or 0,
            "analytics_data": "Analytics feature coming soon"
        } 