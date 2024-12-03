from flask import render_template, Blueprint, request
from model.agent import Agent
from model.app import App
from model.ocr_agent import OCRAgent

from extensions import db
from services.agent_service import AgentService

agents_blueprint = Blueprint('agents', __name__)

'''
Agents
'''
@agents_blueprint.route('/app/<app_id>/agents', methods=['GET'])
def app_agents(app_id):
    app = db.session.query(App).filter(App.app_id == app_id).first()
    return render_template('agents/agents.html', app_id=app_id, app=app)

@agents_blueprint.route('/app/<app_id>/agent/<agent_id>', methods=['GET', 'POST'])
def app_agent(app_id, agent_id):
    agent_service = AgentService()
    if request.method == 'POST':
        agent_data = {
            'agent_id': agent_id,
            'app_id': app_id,
            **request.form.to_dict()
        }
        agent_type = request.form.get('type', 'basic')
        agent = agent_service.create_or_update_agent(agent_data, agent_type)
        return app_agents(app_id)
    
    # Obtener el tipo del query parameter o usar 'basic' como valor por defecto
    agent_type = request.args.get('type', 'basic')
    return agent_service.get_agent_form_data(app_id, agent_id, agent_type)

@agents_blueprint.route('/app/<app_id>/agent/<agent_id>/delete', methods=['GET'])
def app_agent_delete(app_id, agent_id):
    agent_service = AgentService()
    # Obtener el tipo del query parameter
    agent_type = request.args.get('type', 'basic')
    agent_service.delete_agent(agent_id, agent_type)
    return app_agents(app_id)

@agents_blueprint.route('/app/<app_id>/agent/<agent_id>/play', methods=['GET'])
def app_agent_playground(app_id, agent_id):
    agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
    return render_template('agents/playground.html', app_id=app_id, agent=agent)

@agents_blueprint.route('/app/<app_id>/agent/<agent_id>/ocr_play', methods=['GET'])
def app_ocr_playground(app_id, agent_id):
    agent = db.session.query(OCRAgent).filter(OCRAgent.agent_id == agent_id).first()
    return render_template('agents/ocr_playground.html', app_id=app_id, agent=agent)