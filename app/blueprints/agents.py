from flask import render_template, Blueprint, request
from app.model.agent import Agent
from app.model.app import App
from app.model.ocr_agent import OCRAgent
from app.model.model import Model
from app.model.output_parser import OutputParser
from app.model.silo import Silo
from app.extensions import db
from app.services.agent_service import AgentService

agents_blueprint = Blueprint('agents', __name__)

'''
Agents
'''
@agents_blueprint.route('/app/<int:app_id>/agents', methods=['GET'])
def app_agents(app_id: int):
    app = db.session.query(App).filter(App.app_id == app_id).first()
    return render_template('agents/agents.html', app_id=app_id, app=app)

@agents_blueprint.route('/app/<int:app_id>/agent/<int:agent_id>', methods=['GET', 'POST'])
def app_agent(app_id: int, agent_id: int):
    agent_service = AgentService()
    if request.method == 'POST':
        agent_data = {
            'agent_id': agent_id,
            'app_id': app_id,
            **request.form.to_dict()
        }
        agent_type = request.form.get('type', 'agent')
        agent = agent_service.create_or_update_agent(agent_data, agent_type)

        agent_service.update_agent_tools(agent, request.form.getlist('tool_id'))
        return app_agents(app_id)
    
    models = db.session.query(Model).all()
    output_parsers = db.session.query(OutputParser).filter(OutputParser.app_id == app_id).all()
    tools = db.session.query(Agent).filter(Agent.is_tool == True, Agent.app_id == app_id, Agent.agent_id != agent_id).all()
    silos = db.session.query(Silo).filter(Silo.app_id == app_id).all()

    template = 'agents/agent.html'
    agent = Agent(agent_id=0, name="")
    if agent_id != 0:
        agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
        if agent.type == 'ocr_agent':
            template = 'agents/ocr_agent.html'

    return render_template(template, app_id=app_id, agent=agent, models=models, output_parsers=output_parsers, tools=tools, silos=silos)

        

@agents_blueprint.route('/app/<int:app_id>/agent/<int:agent_id>/delete', methods=['GET'])
def app_agent_delete(app_id: int, agent_id: int):
    agent_service = AgentService()
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