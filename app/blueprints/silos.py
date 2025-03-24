from flask import render_template, Blueprint, request, redirect, url_for
from model.silo import Silo
from model.app import App
from model.output_parser import OutputParser
from model.embedding_service import EmbeddingService

from extensions import db
from services.silo_service import SiloService
from services.output_parser_service import OutputParserService
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
    parser_service = OutputParserService()
    if request.method == 'GET':
        output_parsers = db.session.query(OutputParser).all()
        embedding_services = db.session.query(EmbeddingService).all()
        silo = SiloService.get_silo(silo_id)
        if silo is None:
            silo = Silo(name="New Silo", app_id=app_id, silo_id=0)
        
        docs_count = SiloService.count_docs_in_silo(silo_id)
        return render_template('silos/silo.html', 
                             silo=silo, 
                             output_parsers=output_parsers,
                             embedding_services=embedding_services,
                             docs_count=docs_count)
    
    if request.method == 'POST':
        SiloService.create_or_update_silo(request.form)
        return redirect(url_for('silos.silos', app_id=app_id))
    
    silo = SiloService.get_silo(silo_id)
    if silo is None:
        silo = Silo(name="New Silo", app_id=app_id, silo_id=0)
    
    parsers = parser_service.get_parsers_by_app(app_id)

    docs_count = SiloService.count_docs_in_silo(silo_id)
    return render_template('silos/silo.html', silo=silo, output_parsers=parsers, docs_count=docs_count)

@silos_blueprint.route('/<int:silo_id>/delete', methods=['GET'])
def delete(app_id: int, silo_id: int):
    SiloService.delete_silo(silo_id)
    return redirect(url_for('silos.silos', app_id=app_id))

@silos_blueprint.route('/<int:silo_id>/playground', methods=['GET', 'POST'])
def playground(app_id: int, silo_id: int):
    silo = SiloService.get_silo(silo_id)
    results = None
    if request.method == 'POST':
        query = request.form.get('query')
        filter = SiloService.get_metadata_filter_from_form(silo, request.form)
        results = SiloService.find_docs_in_collection(silo_id, query=query, filter_metadata=filter)
    
    return render_template('silos/silo_playground.html', silo=silo, results=results)

@silos_blueprint.route('/<int:silo_id>/content/<string:content_id>/delete', methods=['GET'])
def delete_content(app_id: int, silo_id: int, content_id: str):
    SiloService.delete_content(silo_id, content_id)
    return "OK"
