from flask import render_template, Blueprint, request, redirect, url_for
from extensions import db
from model.ai_service import AIService
from model.ai_service import ProviderEnum
from model.agent import Agent
from model.app import App

TEMPLATE_TO_RENDER = "ai_services.app_ai_services"
ai_services_blueprint = Blueprint('ai_services', __name__, url_prefix='/app/<int:app_id>/ai_services')

@ai_services_blueprint.route('/', methods=['GET'])
def app_ai_services(app_id: int):
    services = db.session.query(AIService).filter(AIService.app_id == app_id).all()
    return render_template('ai_services/ai_services.html', 
                          services=services,
                          app_id=app_id,
                          service_title="AI Services",
                          create_url='ai_services.create_ai_service',
                          edit_url='ai_services.edit_ai_service',
                          delete_url='ai_services.delete_ai_service')

@ai_services_blueprint.route('/<int:service_id>', methods=['GET'])
def ai_service(app_id: int, service_id: int):
    ai_service = db.session.query(AIService).filter(
        AIService.service_id == service_id,
        AIService.app_id == app_id
    ).first()
    return render_template('ai_services/ai_service.html', ai_service=ai_service)

@ai_services_blueprint.route('/<int:service_id>/edit', methods=['GET', 'POST'])
def edit_ai_service(app_id: int, service_id: int):
    ai_service = db.session.query(AIService).filter(
        AIService.service_id == service_id,
        AIService.app_id == app_id
    ).first()
    
    if request.method == 'POST':
        ai_service.name = request.form['name']
        ai_service.description = request.form['description']
        ai_service.provider = request.form['provider']
        ai_service.endpoint = request.form['endpoint']
        ai_service.api_key = request.form['api_key']
        
        db.session.commit()
        return redirect(url_for(TEMPLATE_TO_RENDER, app_id=app_id))
        
    return render_template('ai_services/edit_ai_service.html', 
                         service=ai_service, 
                         providers=ProviderEnum,
                         app_id=app_id,
                         form_title="Edit AI service",
                         submit_button_text="Save changes",
                         cancel_url=TEMPLATE_TO_RENDER)

@ai_services_blueprint.route('/<int:service_id>/delete', methods=['POST'])
def delete_ai_service(app_id: int, service_id: int):
    try:
        # Primero, actualizar los agentes que usan este servicio
        db.session.query(Agent).filter(Agent.service_id == service_id).update({Agent.service_id: None})
        
        # Luego, eliminar el servicio
        ai_service = db.session.query(AIService).filter(
            AIService.service_id == service_id,
            AIService.app_id == app_id
        ).first()
        db.session.delete(ai_service)
        db.session.commit()
        return redirect(url_for(TEMPLATE_TO_RENDER, app_id=app_id))
    except Exception:
        db.session.rollback()
        return redirect(url_for(TEMPLATE_TO_RENDER, app_id=app_id)), 500

@ai_services_blueprint.route('/create', methods=['GET', 'POST'])
def create_ai_service(app_id: int):
    if request.method == 'POST':
        new_service = AIService(
            name=request.form['name'],
            description=request.form['description'],
            provider=request.form['provider'],
            endpoint=request.form['endpoint'],
            api_key=request.form['api_key'],
            app_id=app_id
        )
        
        db.session.add(new_service)
        db.session.commit()
        return redirect(url_for(TEMPLATE_TO_RENDER, app_id=app_id))
        
    return render_template('ai_services/create_ai_service.html', 
                         providers=ProviderEnum,
                         app_id=app_id,
                         form_title="Create new AI service",
                         submit_button_text="Create service",
                         cancel_url=TEMPLATE_TO_RENDER)

