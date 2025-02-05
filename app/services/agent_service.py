from typing import Union, Dict, Any
from flask import render_template
from app.model.agent import Agent
from app.model.ocr_agent import OCRAgent
from app.model.model import Model
from app.model.output_parser import OutputParser
from app.extensions import db
from app.model.silo import Silo
from app.services.silo_service import SiloService

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
        
        if agent_type == 'ocr':
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
    
    @staticmethod
    def _update_normal_agent(agent: Agent, data: dict):
        agent.name = data['name']
        agent.description = data.get('description')
        agent.system_prompt = data.get('system_prompt')
        agent.prompt_template = data.get('prompt_template')
        agent.type = data.get('type')
        agent.status = data.get('status')
        agent.model_id = data.get('model_id')
        agent.app_id = data['app_id']
        agent.silo_id = data.get('silo_id') or None
        agent.has_memory = data.get('has_memory') == 'on'
        agent.output_parser_id = data.get('output_parser_id') or None
    
    @staticmethod
    def get_agent_form_data(app_id: int, agent_id: int, agent_type: str) -> str:
        """
        Obtiene los datos necesarios para renderizar el formulario del agente.
        
        Args:
            app_id: ID de la aplicación
            agent_id: ID del agente a editar (puede ser '0' para nuevo agente)
            agent_type: Tipo de agente ('basic' u 'ocr')
            
        Returns:
            Template renderizado con los datos necesarios
        """
        # Obtener modelos y parsers comunes
        models = db.session.query(Model).all()
        output_parsers = db.session.query(OutputParser).filter(OutputParser.app_id == app_id).all()
        
        # Para nuevo agente
        if agent_id == 0:
            if agent_type == 'ocr':
                return render_template('agents/ocr_agent.html',
                                    app_id=app_id,
                                    agent=OCRAgent(agent_id=0, name=""),
                                    models=models,
                                    output_parsers=output_parsers)
            else:
                return render_template('agents/agent.html',
                                    app_id=app_id,
                                    agent=Agent(agent_id=0, name=""),
                                    models=models,
                                    silos=SiloService.get_silos_by_app_id(app_id),
                                    output_parsers=output_parsers)
        
        # Para agente existente
        if agent_type == 'ocr':
            agent = db.session.query(OCRAgent).filter(OCRAgent.agent_id == agent_id).first()
            return render_template('agents/ocr_agent.html',
                                app_id=app_id,
                                agent=agent,
                                models=models,
                                output_parsers=output_parsers)
        else:
            agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
            return render_template('agents/agent.html',
                                app_id=app_id,
                                agent=agent,
                                models=models,
                                silos=SiloService.get_silos_by_app_id(app_id),
                                output_parsers=output_parsers)
    
    @staticmethod
    def delete_agent(agent_id: int, agent_type: str):
        if agent_type == 'ocr':
            agent = db.session.query(OCRAgent).filter(OCRAgent.agent_id == agent_id).first()
        else:
            agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
        print(agent)
        db.session.delete(agent)
        db.session.commit()
