from flask import render_template, Blueprint, request, redirect, url_for
from app.model.silo import Silo
from app.model.app import App

from app.extensions import db
from app.services.silo_service import SiloService

silos_blueprint = Blueprint('silos', __name__, url_prefix='/app/<int:app_id>/silos')

'''
Silos
'''
@silos_blueprint.route('/', methods=['GET'])
def silos(app_id: int):
    silos = SiloService.get_silos_by_app_id(app_id)
    return render_template('silos/silos.html', app_id=app_id, silos=silos)

@silos_blueprint.route('/<int:silo_id>', methods=['GET', 'POST'])
def silo(app_id: int, silo_id: int):
    if request.method == 'POST':
        SiloService.create_or_update_silo(request.form)
        return redirect(url_for('silos.silos', app_id=app_id))
    
    silo = SiloService.get_silo(silo_id)
    if silo is None:
        silo = Silo(name="New Silo", app_id=app_id, silo_id=0)
    return render_template('silos/silo.html', silo=silo)

@silos_blueprint.route('/<int:silo_id>/delete', methods=['GET'])
def delete(app_id: int, silo_id: int):
    SiloService.delete_silo(silo_id)
    return redirect(url_for('silos.silos', app_id=app_id))
