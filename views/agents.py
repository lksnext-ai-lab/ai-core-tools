from flask import Flask, render_template, session, Blueprint, request, redirect
from model.app import App
from model.agent import Agent
from model.model import Model
from model.repository import Repository

from extensions import db


agents_blueprint = Blueprint('agents', __name__)


'''
Agents
'''
@agents_blueprint.route('/app/<app_id>/agents', methods=['GET'])
def app_agents(app_id):
    app = App.query.filter_by(app_id=app_id).first()
    return render_template('agents/agents.html', app_id=app_id, app=app)

@agents_blueprint.route('/app/<app_id>/agent/<agent_id>', methods=['GET', 'POST'])
def app_agent(app_id, agent_id):
    if request.method == 'POST':
        agent = Agent.query.filter_by(agent_id=agent_id).first()
        if agent is None:
            agent = Agent()
        agent.name = request.form['name']
        agent.description = request.form.get('description')
        agent.system_prompt = request.form.get('system_prompt')
        print(agent.system_prompt)
        agent.prompt_template = request.form.get('prompt_template')
        agent.type = request.form.get('type')
        agent.status = request.form.get('status')
        agent.model_id = request.form.get('model_id')
        agent.app_id = app_id
        agent.repository_id = request.form.get('repository_id')
        if agent.repository_id == '':
            agent.repository_id = None 
        db.session.add(agent)
        db.session.commit()
        return app_agents(app_id)
    agent = Agent.query.filter_by(agent_id=agent_id).first()
    if agent is None:
        agent = Agent(agent_id=0, name="")
    
    models = Model.query.all()
    repositories = Repository.query.filter_by(app_id=app_id).all()
    return render_template('agents/agent.html', app_id=app_id, agent=agent, models=models, repositories=repositories)

@agents_blueprint.route('/app/<app_id>/agent/<agent_id>/delete', methods=['GET'])
def app_agent_delete(app_id, agent_id):
    Agent.query.filter_by(agent_id=agent_id).delete()
    db.session.commit()
    return app_agents(app_id)

@agents_blueprint.route('/app/<app_id>/agent/<agent_id>/play', methods=['GET'])
def app_agent_playground(app_id,  agent_id):
    agent = Agent.query.filter_by(agent_id=agent_id).first()
    return render_template('agents/playground.html', app_id=app_id, agent=agent)
