from flask import render_template, Blueprint, request, redirect, url_for
from app.extensions import db
from app.model.embedding_service import EmbeddingService
from app.model.embedding_service import EmbeddingProvider

embedding_services_blueprint = Blueprint('embedding_services', __name__, url_prefix='/admin/embedding_services')

@embedding_services_blueprint.route('/', methods=['GET'])
def embedding_services():
    services = db.session.query(EmbeddingService).all()
    return render_template('embedding_services/embedding_services.html', 
                          services=services,
                          service_title="Embedding Services",
                          create_url='embedding_services.create_embedding_service',
                          edit_url='embedding_services.edit_embedding_service',
                          delete_url='embedding_services.delete_embedding_service')

@embedding_services_blueprint.route('/<int:service_id>', methods=['GET'])
def embedding_service(service_id):
    service = db.session.query(EmbeddingService).get(service_id)
    return render_template('embedding_services/embedding_service.html', embedding_service=service)

@embedding_services_blueprint.route('/<int:service_id>/edit', methods=['GET', 'POST'])
def edit_embedding_service(service_id):
    service = db.session.query(EmbeddingService).get(service_id)
    
    if request.method == 'POST':
        service.name = request.form['name']
        service.description = request.form['description']
        service.provider = request.form['provider']
        service.endpoint = request.form['endpoint']
        service.api_key = request.form['api_key']
        
        db.session.commit()
        return redirect(url_for('embedding_services.embedding_services'))
        
    return render_template('embedding_services/edit_embedding_service.html', 
                         service=service, 
                         providers=EmbeddingProvider,
                         form_title="Edit embedding service",
                         submit_button_text="Save changes",
                         cancel_url='embedding_services.embedding_services')

@embedding_services_blueprint.route('/<int:service_id>/delete', methods=['POST'])
def delete_embedding_service(service_id):
    try:
        # Aquí podrías añadir lógica similar a la de AI Services para actualizar entidades que usen este servicio
        
        service = db.session.query(EmbeddingService).get(service_id)
        db.session.delete(service)
        db.session.commit()
        return redirect(url_for('embedding_services.embedding_services'))
    except Exception as e:
        db.session.rollback()
        return redirect(url_for('embedding_services.embedding_services')), 500

@embedding_services_blueprint.route('/create', methods=['GET', 'POST'])
def create_embedding_service():
    if request.method == 'POST':
        new_service = EmbeddingService(
            name=request.form['name'],
            description=request.form['description'],
            provider=request.form['provider'],
            endpoint=request.form['endpoint'],
            api_key=request.form['api_key']
        )
        
        db.session.add(new_service)
        db.session.commit()
        return redirect(url_for('embedding_services.embedding_services'))
        
    return render_template('embedding_services/create_embedding_service.html', 
                         providers=EmbeddingProvider,
                         form_title="Create new embedding service",
                         submit_button_text="Create service",
                         cancel_url='embedding_services.embedding_services')