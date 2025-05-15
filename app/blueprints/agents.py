from flask import render_template, Blueprint, request
from model.silo import Silo
from model.agent import Agent
from model.app import App
from model.ocr_agent import OCRAgent
from model.ai_service import AIService
from model.output_parser import OutputParser
from model.silo import Silo
from model.mcp_config import MCPConfig
from extensions import db
from services.agent_service import AgentService
from services.agent_cache_service import AgentCacheService
import logging

agents_blueprint = Blueprint('agents', __name__)
logger = logging.getLogger(__name__)

'''
Agents
'''
@agents_blueprint.route('/app/<int:app_id>/agents', methods=['GET'])
def app_agents(app_id: int):
    app = db.session.query(App).filter(App.app_id == app_id).first()
    agents = AgentService().get_agents(app_id)
    return render_template('agents/agents.html', app_id=app_id, app=app, agents=agents)

@agents_blueprint.route('/app/<int:app_id>/agent/<int:agent_id>', methods=['GET'])
def app_agent_get(app_id: int, agent_id: int):
    agent_service = AgentService()
    
    #TODO: avoid using db session from blueprints. Move to services
    ai_services = db.session.query(AIService).filter(AIService.app_id == app_id).all()
    silos = db.session.query(Silo).filter(Silo.app_id == app_id).all()
    output_parsers = db.session.query(OutputParser).filter(OutputParser.app_id == app_id).all()
    tools = db.session.query(Agent).filter(Agent.is_tool == True, Agent.app_id == app_id, Agent.agent_id != agent_id).all()
    mcp_configs = db.session.query(MCPConfig).filter(MCPConfig.app_id == app_id).all()

    template = 'agents/agent.html'
    agent = Agent(agent_id=0, name="")
    if agent_id != 0:
        agent = agent_service.get_agent(agent_id)
        if agent.type == 'ocr_agent':
            agent = agent_service.get_agent(agent_id, 'ocr')
            template = 'agents/ocr_agent.html'

    return render_template(template, app_id=app_id, agent=agent, ai_services=ai_services, 
                         output_parsers=output_parsers, tools=tools, silos=silos, mcp_configs=mcp_configs)

@agents_blueprint.route('/app/<int:app_id>/agent/<int:agent_id>', methods=['POST'])
def app_agent_post(app_id: int, agent_id: int):
    agent_service = AgentService()
    agent_data = {
        'agent_id': agent_id,
        'app_id': app_id,
        **request.form.to_dict()
    }
    logger.info(f"agent_data: {agent_data}")
    agent_type = request.form.get('type', 'agent')
    agent = agent_service.create_or_update_agent(agent_data, agent_type)
    
    # Invalidate agent cache when updated
    AgentCacheService.invalidate_agent(agent_id)

    # Update tools and MCPs
    agent_service.update_agent_tools(agent, request.form.getlist('tool_id'), request.form)
    agent_service.update_agent_mcps(agent, request.form.getlist('mcp_config_id'), request.form)
    
    return app_agents(app_id)

@agents_blueprint.route('/app/<int:app_id>/agent/<int:agent_id>/delete', methods=['POST'])
def app_agent_delete(app_id: int, agent_id: int):
    agent_service = AgentService()
    # Invalidate agent cache when deleted
    AgentCacheService.invalidate_agent(agent_id)
    agent_service.delete_agent(agent_id)
    return app_agents(app_id)

@agents_blueprint.route('/app/<int:app_id>/agent/<int:agent_id>/play', methods=['GET'])
def app_agent_playground(app_id: int, agent_id: int):
    agent = db.session.query(Agent).filter(Agent.agent_id == int(agent_id)).first()
    return render_template('agents/playground.html', app_id=app_id, agent=agent)

@agents_blueprint.route('/app/<int:app_id>/agent/<int:agent_id>/ocr_play', methods=['GET'])
def app_ocr_playground(app_id: int, agent_id: int):
    agent = db.session.query(OCRAgent).filter(OCRAgent.agent_id == int(agent_id)).first()
    return render_template('agents/ocr_playground.html', app_id=app_id, agent=agent)