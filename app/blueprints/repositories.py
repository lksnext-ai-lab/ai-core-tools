from flask import render_template, Blueprint, request, redirect, url_for
from model.repository import Repository
from model.resource import Resource
from model.silo import Silo
from model.agent import Agent
from extensions import db
from tools.pgVectorTools import PGVectorTools
from services.silo_service import SiloService
from model.silo import SiloType
import os
from dotenv import load_dotenv
from services.repository_service import RepositoryService
from services.output_parser_service import OutputParserService
from services.embedding_service_service import EmbeddingServiceService
from model.embedding_service import EmbeddingService
#TODO: should be accesed from silo service

load_dotenv()
pgVectorTools = PGVectorTools(db)

REPO_BASE_FOLDER = os.getenv("REPO_BASE_FOLDER")

repositories_blueprint = Blueprint('repositories', __name__)

@repositories_blueprint.route('/app/<int:app_id>/repositories', methods=['GET'])
def repositories(app_id: int):
    repos = RepositoryService.get_repositories_by_app_id(app_id)
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
            repo = RepositoryService.get_repository(repository_id)
            repo.name = request.form['name']
            embedding_service_id = request.form.get('embedding_service_id')
            
            repo = RepositoryService.update_repository(repo, embedding_service_id)
        
        return redirect(url_for('repositories.repositories', app_id=app_id))
    
    embedding_services = EmbeddingServiceService.get_embedding_services_by_app_id(app_id)

    if repository_id == 0:
        repo = Repository(name="New Repository", app_id=app_id, repository_id=0)
        return render_template('repositories/repository.html', 
                             app_id=app_id, 
                             repo=repo, 
                             embedding_services=embedding_services)

    repo = RepositoryService.get_repository(repository_id)
    return render_template('repositories/resources.html', 
                         app_id=app_id, 
                         repo=repo, 
                         embedding_services=embedding_services)

@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>/settings', methods=['GET', 'POST'])
def repository_settings(app_id: int, repository_id: int):
    repo = RepositoryService.get_repository(repository_id)
    
    if request.method == 'POST':
        repo.name = request.form['name']
        embedding_service_id = request.form.get('embedding_service_id')
        
        # Actualizar el embedding service del silo asociado
        if repo.silo:
            repo.silo.embedding_service_id = embedding_service_id if embedding_service_id else None
            
        db.session.commit()
        return redirect(url_for('repositories.repositories', app_id=app_id))
    
    embedding_services = EmbeddingServiceService.get_embedding_services_by_app_id(app_id)
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
        if file.filename == '':
            return redirect(request.url)
        if file:
            repository_path = os.path.join(REPO_BASE_FOLDER, str(repository_id))
            os.makedirs(repository_path, exist_ok=True)
            
            file_path = os.path.join(repository_path, file.filename)
            file.save(file_path)
            
            resource = Resource(name=request.form['name'], uri=file.filename, repository_id=repository_id)
            db.session.add(resource)
            db.session.commit()
            db.session.refresh(resource)
            
            SiloService.index_resource(resource)
        
        return redirect(url_for('repositories.repository', app_id=app_id, repository_id=repository_id))