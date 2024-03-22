from flask import Flask, render_template, session, Blueprint, request, redirect
from model.repository import Repository
from model.resource import Resource
from model.agent import Agent

from extensions import db


repositories_blueprint = Blueprint('repositories', __name__)

@repositories_blueprint.route('/app/<app_id>/repositories', methods=['GET'])
def repositories(app_id):
    repos = Repository.query.filter_by(app_id=app_id).all()
    return render_template('repositories/repositories.html', repos=repos)

@repositories_blueprint.route('/app/<app_id>/repository/<repository_id>', methods=['GET'])
def repository(app_id, repository_id):
    repo = Repository.query.filter_by(repository_id=repository_id).first()
    return render_template('repositories/repository.html', app_id=app_id, repo=repo)


@repositories_blueprint.route('/app/<app_id>/repository/<repository_id>/settings', methods=['GET'])
def repository_settings(app_id, repository_id):
    repo = Repository.query.filter_by(repository_id=repository_id).first()
    return render_template('repositories/settings.html', app_id=app_id, repo=repo)

'''
Resources
'''
@repositories_blueprint.route('/app/<app_id>/repository/<repository_id>/resource/<resource_id>/delete', methods=['GET'])
def resource_delete(app_id, repository_id, resource_id):
    Resource.query.filter_by(resource_id=resource_id).delete()
    db.session.commit()
    return repository(app_id, repository_id)

@repositories_blueprint.route('/app/<app_id>/repository/<repository_id>/resource', methods=['POST'])
def resource_create(app_id, repository_id):
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        # if user does not select file, browser submits an empty file with no filename
        if file.filename == '':
            return redirect(request.url)
        if file : #and allowed_file(file.filename):
            
            resource = Resource(name=request.form['name'], uri=file.filename, repository_id=repository_id)
            
            db.session.add(resource)
            db.session.commit()

        return repository(app_id, repository_id)


'''
Agents
'''
@repositories_blueprint.route('/app/<app_id>/repository/<repository_id>/agents', methods=['GET'])
def repository_agents(app_id, repository_id):
    repo = Repository.query.filter_by(repository_id=repository_id).first()
    return render_template('repositories/agents.html', app_id=app_id, repo=repo)

@repositories_blueprint.route('/app/<app_id>/repository/<repository_id>/agent/<agent_id>', methods=['GET', 'POST'])
def repository_agent(app_id, repository_id, agent_id):
    if request.method == 'POST':
        agent = Agent.query.filter_by(agent_id=agent_id).first()
        if agent is None:
            agent = Agent()
        agent.name = request.form['name']
        agent.description = request.form.get('description')
        agent.system_prompt = request.form.get('system_prompt')
        agent.prompt_template = request.form.get('prompt_template')
        agent.type = request.form.get('type')
        agent.status = request.form.get('status')
        agent.model = request.form.get('model')
        agent.repository_id = repository_id
        db.session.add(agent)
        db.session.commit()
        return repository_agents(app_id, repository_id)
    repo = Repository.query.filter_by(repository_id=repository_id).first()
    agent = Agent.query.filter_by(agent_id=agent_id).first()
    if agent is None:
        agent = Agent(agent_id=0, name="")
        
    return render_template('repositories/agent.html', app_id=app_id, repo=repo, agent=agent)

@repositories_blueprint.route('/app/<app_id>/repository/<repository_id>/agent/<agent_id>/delete', methods=['GET'])
def repository_agent_delete(app_id, repository_id, agent_id):
    Agent.query.filter_by(agent_id=agent_id).delete()
    db.session.commit()
    return repository_agents(app_id, repository_id)

@repositories_blueprint.route('/app/<app_id>/repository/<repository_id>/agent/<agent_id>/play', methods=['GET'])
def repository_playground(app_id, repository_id, agent_id):
    repo = Repository.query.filter_by(repository_id=repository_id).first()
    agent = Agent.query.filter_by(agent_id=agent_id).first()
    return render_template('repositories/playground.html', app_id=app_id, repo=repo, agent=agent)
