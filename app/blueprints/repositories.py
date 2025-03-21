from flask import render_template, Blueprint, request, redirect, url_for
from app.model.repository import Repository
from app.model.resource import Resource
from app.model.silo import Silo
from app.model.agent import Agent
from app.extensions import db
from app.tools.pgVectorTools import PGVectorTools
from app.services.silo_service import SiloService
from app.model.silo import SiloType
import os
from app.services.repository_service import RepositoryService
from app.services.output_parser_service import OutputParserService
from app.model.embedding_service import EmbeddingService
#TODO: should be accesed from silo service
pgVectorTools = PGVectorTools(db)

REPO_BASE_FOLDER = os.getenv("REPO_BASE_FOLDER")

repositories_blueprint = Blueprint('repositories', __name__)

@repositories_blueprint.route('/app/<int:app_id>/repositories', methods=['GET'])
def repositories(app_id: int):
    repos = db.session.query(Repository).filter(Repository.app_id == app_id).all()
    return render_template('repositories/repositories.html', repos=repos)

@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>', methods=['GET', 'POST'])
def repository(app_id: int, repository_id: int):
    if request.method == 'POST':
        if repository_id == 0:
            # Crear nuevo repositorio
            repo = Repository()
            repo.name = request.form['name']
            repo.type = request.form.get('type')
            repo.status = request.form.get('status')
            repo.app_id = app_id
            embedding_service_id = request.form.get('embedding_service_id')
            
            repo = RepositoryService.create_repository(repo, embedding_service_id)
        else:
            # Actualizar repositorio existente
            repo = db.session.query(Repository).filter(Repository.repository_id == repository_id).first()
            repo.name = request.form['name']
            embedding_service_id = request.form.get('embedding_service_id')
            
            repo = RepositoryService.update_repository(repo, embedding_service_id)
        
        return redirect(url_for('repositories.repositories', app_id=app_id))

    if repository_id == 0:
        repo = Repository(name="New Repository", app_id=app_id, repository_id=0)
        embedding_services = db.session.query(EmbeddingService).all()
        return render_template('repositories/repository.html', 
                             app_id=app_id, 
                             repo=repo, 
                             embedding_services=embedding_services)

    repo = db.session.query(Repository).filter(Repository.repository_id == repository_id).first()
    embedding_services = db.session.query(EmbeddingService).all()
    return render_template('repositories/repository.html', 
                         app_id=app_id, 
                         repo=repo, 
                         embedding_services=embedding_services)

@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>/settings', methods=['GET', 'POST'])
def repository_settings(app_id: int, repository_id: int):
    repo = db.session.query(Repository).filter(Repository.repository_id == repository_id).first()
    
    if request.method == 'POST':
        repo.name = request.form['name']
        embedding_service_id = request.form.get('embedding_service_id')
        
        # Actualizar el embedding service del silo asociado
        if repo.silo:
            repo.silo.embedding_service_id = embedding_service_id if embedding_service_id else None
            
        db.session.commit()
        return redirect(url_for('repositories.repositories', app_id=app_id))
    
    embedding_services = db.session.query(EmbeddingService).all()
    return render_template('repositories/repository.html', 
                         app_id=app_id, 
                         repo=repo, 
                         embedding_services=embedding_services)

@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>/delete', methods=['GET'])
def repository_delete(app_id: int, repository_id: int):
    '''repo = db.session.query(Repository).filter(Repository.repository_id == repository_id).first()
    db.session.query(Resource).filter(Resource.repository_id == repository_id).delete()
    db.session.query(Repository).filter(Repository.repository_id == repository_id).delete()
    db.session.query(Silo).filter(Silo.silo_id == repo.silo_id).delete()
    #TODO: empty silo
    db.session.commit()'''
    repo = RepositoryService.get_repository(repository_id)
    RepositoryService.delete_repository(repo)
    return repositories(app_id)

    
'''
Resources
'''
@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>/resource/<int:resource_id>/delete', methods=['GET'])
def resource_delete(app_id: int, repository_id: int, resource_id: int):
    resource = db.session.query(Resource).filter(Resource.resource_id == resource_id).first()
    SiloService.delete_resource(resource)
    db.session.query(Resource).filter(Resource.resource_id == resource_id).delete()
    db.session.commit()
    return repository(app_id, repository_id)

@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>/resource', methods=['POST'])
def resource_create(app_id: int, repository_id: int):
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        # if user does not select file, browser submits an empty file with no filename
        if file.filename == '':
            return redirect(request.url)
        if file : #and allowed_file(file.filename):
            file.save(os.path.join(REPO_BASE_FOLDER, str(repository_id), file.filename))
            resource = Resource(name=request.form['name'], uri=file.filename, repository_id=repository_id)
            
            db.session.add(resource)
            db.session.commit()
            db.session.refresh(resource)
            
            SiloService.index_resource(resource)
        
        return redirect(url_for('repositories.repository', app_id=app_id, repository_id=repository_id))

'''
Agents
'''
@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>/agents', methods=['GET'])
def repository_agents(app_id: int, repository_id: int):
    repo = db.session.query(Repository).filter(Repository.repository_id == repository_id).first()
    return render_template('repositories/agents.html', app_id=app_id, repo=repo)

@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>/agent/<int:agent_id>', methods=['GET', 'POST'])
def repository_agent(app_id: int, repository_id: int, agent_id: int):
    if request.method == 'POST':
        agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
        if agent is None:
            agent = Agent()
        agent.name = request.form['name']
        agent.description = request.form.get('description')
        agent.system_prompt = request.form.get('system_prompt')
        print(agent.system_prompt)
        agent.prompt_template = request.form.get('prompt_template')
        agent.type = request.form.get('type')
        agent.status = request.form.get('status')
        agent.model = request.form.get('model')
        agent.repository_id = repository_id
        db.session.add(agent)
        db.session.commit()
        return repository_agents(app_id, repository_id)
    repo = db.session.query(Repository).filter(Repository.repository_id == repository_id).first()
    agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
    if agent is None:
        agent = Agent(agent_id=0, name="")
        
    return render_template('repositories/agent.html', app_id=app_id, repo=repo, agent=agent)

@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>/agent/<int:agent_id>/delete', methods=['GET'])
def repository_agent_delete(app_id: int, repository_id: int, agent_id: int):
    db.session.query(Agent).filter(Agent.agent_id == agent_id).delete()
    db.session.commit()
    return repository_agents(app_id, repository_id)

@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>/agent/<int:agent_id>/play', methods=['GET'])
def repository_playground(app_id: int, repository_id: int, agent_id: int):
    repo = db.session.query(Repository).filter(Repository.repository_id == repository_id).first()
    agent = db.session.query(Agent).filter(Agent.agent_id == agent_id).first()
    return render_template('repositories/playground.html', app_id=app_id, repo=repo, agent=agent)
