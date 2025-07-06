from flask import render_template, Blueprint, request, jsonify
from flask_login import login_required
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
from utils.pricing_decorators import check_usage_limit, require_feature
from utils.decorators import validate_app_access
import logging

agents_blueprint = Blueprint('agents', __name__)
logger = logging.getLogger(__name__)

'''
Agents
'''
@agents_blueprint.route('/app/<int:app_id>/agents', methods=['GET'])
@login_required
@validate_app_access
def app_agents(app_id: int, app=None):
    agents = AgentService().get_agents(app_id)
    return render_template('agents/agents.html', app_id=app_id, app=app, agents=agents)

@agents_blueprint.route('/app/<int:app_id>/agent/<int:agent_id>', methods=['GET'])
@login_required
@validate_app_access
def app_agent_get(app_id: int, agent_id: int, app=None):
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
@login_required
@validate_app_access
@check_usage_limit('agents')  # Check agent creation limits
def app_agent_post(app_id: int, agent_id: int, app=None):
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
@login_required
@validate_app_access
def app_agent_delete(app_id: int, agent_id: int, app=None):
    agent_service = AgentService()
    # Invalidate agent cache when deleted
    AgentCacheService.invalidate_agent(agent_id)
    agent_service.delete_agent(agent_id)
    return app_agents(app_id)

@agents_blueprint.route('/app/<int:app_id>/agent/<int:agent_id>/play', methods=['GET'])
@login_required
@validate_app_access
def app_agent_playground(app_id: int, agent_id: int, app=None):
    agent = db.session.query(Agent).filter(Agent.agent_id == int(agent_id)).first()
    return render_template('agents/playground.html', app_id=app_id, agent=agent)

@agents_blueprint.route('/app/<int:app_id>/agent/<int:agent_id>/analytics', methods=['GET'])
@login_required
@validate_app_access
@require_feature('advanced_analytics')
def app_agent_analytics(app_id: int, agent_id: int, app=None):
    """Advanced analytics - premium feature"""
    agent = db.session.query(Agent).filter(Agent.agent_id == int(agent_id)).first()
    return render_template('agents/analytics.html', app_id=app_id, agent=agent)

@agents_blueprint.route('/app/<int:app_id>/agent/<int:agent_id>/ocr_play', methods=['GET'])
@login_required
@validate_app_access
def app_ocr_playground(app_id: int, agent_id: int, app=None):
    agent = db.session.query(OCRAgent).filter(OCRAgent.agent_id == int(agent_id)).first()
    return render_template('agents/ocr_playground.html', app_id=app_id, agent=agent)

@agents_blueprint.route('/agents/<int:agent_id>/update-prompt', methods=['POST'])
@login_required
def update_agent_prompt(agent_id: int):
    """Update agent system prompt or prompt template via API"""
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        prompt_type = data.get('type')
        new_prompt = data.get('prompt')
        
        if not prompt_type or not new_prompt:
            return jsonify({'success': False, 'error': 'Missing type or prompt data'}), 400
        
        if prompt_type not in ['system', 'template']:
            return jsonify({'success': False, 'error': 'Invalid prompt type'}), 400
        
        # Get agent
        agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
        if not agent:
            return jsonify({'success': False, 'error': 'Agent not found'}), 404
        
        # Update the appropriate prompt
        if prompt_type == 'system':
            agent.system_prompt = new_prompt
        elif prompt_type == 'template':
            agent.prompt_template = new_prompt
        
        # Save changes
        db.session.commit()
        
        # Invalidate agent cache
        AgentCacheService.invalidate_agent(agent_id)
        
        logger.info(f"Updated {prompt_type} prompt for agent {agent_id}")
        
        return jsonify({
            'success': True, 
            'message': f'{prompt_type.capitalize()} prompt updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating prompt for agent {agent_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

