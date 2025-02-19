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
        
        if agent_type == 'ocr_agent':
            if not agent:
                agent = OCRAgent()
            AgentService._update_ocr_agent(agent, agent_data)
        else:
            if not agent:
                agent = Agent()
            AgentService._update_normal_agent(agent, agent_data)
            
        db.session.add(agent)
        db.session.commit()
        return agent
    
    @staticmethod
    def _update_ocr_agent(agent: OCRAgent, data: dict):
        agent.name = data['name']
        agent.description = data.get('description')
        agent.vision_model_id = data.get('vision_model_id') or agent.vision_model_id
        agent.vision_system_prompt = data.get('vision_system_prompt') or agent.vision_system_prompt
        agent.model_id = data.get('model_id')
        agent.text_system_prompt = data.get('text_system_prompt')
        agent.output_parser_id = data.get('output_parser_id') or None
        agent.app_id = data['app_id']
        agent.is_tool = data.get('is_tool') == 'on'
    
    @staticmethod
    def _update_normal_agent(agent: Agent, data: dict):
        agent.name = data['name']
        agent.description = data.get('description')
        agent.system_prompt = data.get('system_prompt')
        agent.prompt_template = data.get('prompt_template')
        agent.status = data.get('status')
        agent.model_id = data.get('model_id')
        agent.app_id = data['app_id']
        agent.silo_id = data.get('silo_id') or None
        agent.has_memory = data.get('has_memory') == 'on'
        agent.output_parser_id = data.get('output_parser_id') or None
        agent.is_tool = data.get('is_tool') == 'on'

    @staticmethod
    def update_agent_tools(agent: Agent, tool_ids: list):
        # Convert tool_ids to integers
        ids = [int(tool_id) for tool_id in tool_ids]
        agent.tools = db.session.query(Agent).filter(Agent.agent_id.in_(ids)).all()
        db.session.commit()
    
    @staticmethod
    def delete_agent(agent_id: int):
        agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
        print(agent)
        db.session.delete(agent)
        db.session.commit()
