from flask import render_template, Blueprint, request, redirect, url_for, send_file, flash
from flask_login import login_required
from model.repository import Repository
from model.silo import Silo
from model.agent import Agent
from extensions import db
from tools.pgVectorTools import PGVectorTools
from model.silo import SiloType
import os
from dotenv import load_dotenv
from services.repository_service import RepositoryService
from services.output_parser_service import OutputParserService
from services.embedding_service_service import EmbeddingServiceService
from services.resource_service import ResourceService
from model.embedding_service import EmbeddingService
from utils.decorators import validate_app_access

load_dotenv()
pgVectorTools = PGVectorTools(db)

REPO_BASE_FOLDER = os.path.abspath(os.getenv("REPO_BASE_FOLDER"))

repositories_blueprint = Blueprint('repositories', __name__)

def _validate_resource_form(request):
    """
    Validate resource creation form data
    
    Args:
        request: Flask request object
        
    Returns:
        tuple: (file, errors) where file is the uploaded file or None, 
               and errors is a list of validation error messages
    """
    errors = []
    
    # Check if file was uploaded
    if 'file' not in request.files:
        errors.append('No file selected. Please choose a file to upload.')
        return None, errors
    
    file = request.files['file']
    
    # Check if file has a name
    if file.filename == '':
        errors.append('No file selected. Please choose a file to upload.')
        return None, errors
    
    # Validate resource name
    name = request.form.get('name', '').strip()
    if not name:
        errors.append('Resource name is required. Please provide a name for the resource.')
    
    return file, errors

@repositories_blueprint.route('/app/<int:app_id>/repositories', methods=['GET'])
@login_required
@validate_app_access
def repositories(app_id: int, app=None):
    repos = RepositoryService.get_repositories_by_app_id(app_id)
    return render_template('repositories/repositories.html', repos=repos)

@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>', methods=['GET', 'POST'])
@login_required
@validate_app_access
def repository(app_id: int, repository_id: int, app=None):
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
@login_required
@validate_app_access
def repository_settings(app_id: int, repository_id: int, app=None):
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
@login_required
@validate_app_access
def repository_delete(app_id: int, repository_id: int, app=None):
    repo = RepositoryService.get_repository(repository_id)
    if repo:
        RepositoryService.delete_repository(repo)
    return redirect(url_for('repositories.repositories', app_id=app_id))

    
'''
Resources
'''
@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>/resource/<int:resource_id>/delete', methods=['GET'])
@login_required
@validate_app_access
def resource_delete(app_id: int, repository_id: int, resource_id: int, app=None):
    success = ResourceService.delete_resource(resource_id)
    if success:
        flash('Resource deleted successfully', 'success')
    else:
        flash('Failed to delete resource. Resource may not exist or could not be removed.', 'error')
    return redirect(url_for('repositories.repository', app_id=app_id, repository_id=repository_id))

@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>/resource', methods=['POST'])
@login_required
@validate_app_access
def resource_create(app_id: int, repository_id: int, app=None):
    if request.method == 'POST':
        # Validate form data
        file, errors = _validate_resource_form(request)
        
        # If validation errors exist, show them and redirect back
        if errors:
            for error in errors:
                flash(error, 'error')
            return redirect(request.url)
        
        try:
            # Create resource using service
            name = request.form.get('name', '').strip()
            ResourceService.create_resource_from_file(file, name, repository_id)
            flash(f'Resource "{name}" created and indexed successfully', 'success')
            
        except ValueError as e:
            flash(f'Validation error: {str(e)}', 'error')
        except Exception as e:
            flash(f'Error creating resource: {str(e)}', 'error')
        
        return redirect(url_for('repositories.repository', app_id=app_id, repository_id=repository_id))

@repositories_blueprint.route('/app/<int:app_id>/repository/<int:repository_id>/resource/<int:resource_id>/download', methods=['GET'])
@login_required
@validate_app_access
def resource_download(app_id: int, repository_id: int, resource_id: int, app=None):
    resource = ResourceService.get_resource(resource_id)
    if not resource:
        flash('Resource not found', 'error')
        return redirect(url_for('repositories.repository', app_id=app_id, repository_id=repository_id))
    
    file_path = ResourceService.get_resource_file_path(resource_id)
    if not file_path or not os.path.exists(file_path):
        flash('File not found on disk. The file may have been moved or deleted.', 'error')
        return redirect(url_for('repositories.repository', app_id=app_id, repository_id=repository_id))
    
    return send_file(file_path, as_attachment=True, download_name=resource.uri)