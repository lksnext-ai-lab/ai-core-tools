from flask import render_template, Blueprint, request, redirect, url_for
from app.extensions import db
from app.model.ai_service import AIService
from app.model.ai_service import ProviderEnum
from app.model.agent import Agent
from app.model.app import App

ai_services_blueprint = Blueprint('ai_services', __name__, url_prefix='/admin/ai_services')

@ai_services_blueprint.route('/', methods=['GET'])
def ai_services():
    services = db.session.query(AIService).all()
    return render_template('ai_services/ai_services.html', 
                          services=services,
                          service_title="AI Services",
                          create_url='ai_services.create_ai_service',
                          edit_url='ai_services.edit_ai_service',
                          delete_url='ai_services.delete_ai_service')

@ai_services_blueprint.route('/<int:service_id>', methods=['GET'])
def ai_service(service_id):
    ai_service = db.session.query(AIService).get(service_id)
    return render_template('ai_services/ai_service.html', ai_service=ai_service)

@ai_services_blueprint.route('/<int:service_id>/edit', methods=['GET', 'POST'])
def edit_ai_service(service_id):
    ai_service = db.session.query(AIService).get(service_id)
    
    if request.method == 'POST':
        ai_service.name = request.form['name']
        ai_service.description = request.form['description']
        ai_service.provider = request.form['provider']
        ai_service.endpoint = request.form['endpoint']
        ai_service.api_key = request.form['api_key']
        ai_service.app_id = request.form['app_id']
        
        db.session.commit()
        return redirect(url_for('ai_services.ai_services'))
        
    apps = db.session.query(App).all()
    return render_template('ai_services/edit_ai_service.html', 
                         service=ai_service, 
                         providers=ProviderEnum,
                         apps=apps,
                         form_title="Edit AI service",
                         submit_button_text="Save changes",
                         cancel_url='ai_services.ai_services')

@ai_services_blueprint.route('/<int:service_id>/delete', methods=['POST'])
def delete_ai_service(service_id):
    try:
        # Primero, actualizar los agentes que usan este servicio
        db.session.query(Agent).filter(Agent.service_id == service_id).update({Agent.service_id: None})
        
        # Luego, eliminar el servicio
        ai_service = db.session.query(AIService).get(service_id)
        db.session.delete(ai_service)
        db.session.commit()
        return redirect(url_for('ai_services.ai_services'))
    except Exception as e:
        db.session.rollback()
        # Aquí podrías agregar un mensaje flash para informar del error
        return redirect(url_for('ai_services.ai_services')), 500

@ai_services_blueprint.route('/create', methods=['GET', 'POST'])
def create_ai_service():
    if request.method == 'POST':
        new_service = AIService(
            name=request.form['name'],
            description=request.form['description'],
            provider=request.form['provider'],
            endpoint=request.form['endpoint'],
            api_key=request.form['api_key'],
            app_id=request.form['app_id']
        )
        
        db.session.add(new_service)
        db.session.commit()
        return redirect(url_for('ai_services.ai_services'))
        
    apps = db.session.query(App).all()
    return render_template('ai_services/create_ai_service.html', 
                         providers=ProviderEnum,
                         apps=apps,
                         form_title="Create new AI service",
                         submit_button_text="Create service",
                         cancel_url='ai_services.ai_services')

