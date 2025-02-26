from flask import render_template, Blueprint, request, redirect, url_for
from app.extensions import db
from app.model.ai_service import AIService
ai_services_blueprint = Blueprint('ai_services', __name__, url_prefix='/admin/ai_services')

@ai_services_blueprint.route('/', methods=['GET'])
def ai_services():
    ai_services = db.session.query(AIService).all()
    return render_template('ai_services/ai_services.html', ai_services=ai_services)

@ai_services_blueprint.route('/<int:service_id>', methods=['GET'])
def ai_service(service_id):
    ai_service = db.session.query(AIService).get(service_id)
    return render_template('ai_services/ai_service.html', ai_service=ai_service)

