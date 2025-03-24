from flask import render_template, Blueprint, request, redirect, url_for
from extensions import db
from model.embedding_service import EmbeddingService
from model.embedding_service import EmbeddingProvider
from model.app import App

embedding_services_blueprint = Blueprint('embedding_services', __name__, url_prefix='/app/<int:app_id>/embedding_services')

@embedding_services_blueprint.route('/', methods=['GET'])
def app_embedding_services(app_id: int):
    services = db.session.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).all()
    return render_template('embedding_services/embedding_services.html', 
                          services=services,
                          app_id=app_id,
                          service_title="Embedding Services",
                          create_url='embedding_services.create_embedding_service',
                          edit_url='embedding_services.edit_embedding_service',
                          delete_url='embedding_services.delete_embedding_service')

@embedding_services_blueprint.route('/<int:service_id>', methods=['GET'])
def embedding_service(app_id: int, service_id: int):
    service = db.session.query(EmbeddingService).filter(
        EmbeddingService.service_id == service_id,
        EmbeddingService.app_id == app_id
    ).first()
    return render_template('embedding_services/embedding_service.html', embedding_service=service)

@embedding_services_blueprint.route('/<int:service_id>/edit', methods=['GET', 'POST'])
def edit_embedding_service(app_id: int, service_id: int):
    service = db.session.query(EmbeddingService).filter(
        EmbeddingService.service_id == service_id,
        EmbeddingService.app_id == app_id
    ).first()
    
    if request.method == 'POST':
        service.name = request.form['name']
        service.description = request.form['description']
        service.provider = request.form['provider']
        service.endpoint = request.form['endpoint']
        service.api_key = request.form['api_key']
        
        db.session.commit()
        return redirect(url_for('embedding_services.app_embedding_services', app_id=app_id))
        
    return render_template('embedding_services/edit_embedding_service.html', 
                         service=service, 
                         providers=EmbeddingProvider,
                         app_id=app_id,
                         form_title="Edit embedding service",
                         submit_button_text="Save changes",
                         cancel_url='embedding_services.app_embedding_services')

@embedding_services_blueprint.route('/<int:service_id>/delete', methods=['POST'])
def delete_embedding_service(app_id: int, service_id: int):
    try:
        service = db.session.query(EmbeddingService).filter(
            EmbeddingService.service_id == service_id,
            EmbeddingService.app_id == app_id
        ).first()
        db.session.delete(service)
        db.session.commit()
        return redirect(url_for('embedding_services.app_embedding_services', app_id=app_id))
    except Exception as e:
        db.session.rollback()
        return redirect(url_for('embedding_services.app_embedding_services', app_id=app_id)), 500

@embedding_services_blueprint.route('/create', methods=['GET', 'POST'])
def create_embedding_service(app_id: int):
    if request.method == 'POST':
        new_service = EmbeddingService(
            name=request.form['name'],
            description=request.form['description'],
            provider=request.form['provider'],
            endpoint=request.form['endpoint'],
            api_key=request.form['api_key'],
            app_id=app_id
        )
        
        db.session.add(new_service)
        db.session.commit()
        return redirect(url_for('embedding_services.app_embedding_services', app_id=app_id))
        
    return render_template('embedding_services/create_embedding_service.html', 
                         providers=EmbeddingProvider,
                         app_id=app_id,
                         form_title="Create new embedding service",
                         submit_button_text="Create service",
                         cancel_url='embedding_services.app_embedding_services')