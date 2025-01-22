from flask import session, Blueprint, request, jsonify, request
from app.model.silo import Silo
from app.extensions import db
from sqlalchemy import text
from app.services.silo_service import SiloService
api_silo_blueprint = Blueprint('silo', __name__, url_prefix='/api/silo/app/<int:app_id>/silos')

@api_silo_blueprint.route('/', methods=['GET'])
def get_silos(app_id: int):
    silos = db.session.query(Silo).filter(Silo.app_id == app_id).all()
    sql = text("SELECT * FROM langchain_pg_embedding WHERE cmetadata @> '{\"topic\": \"animals\"}';")
    result = db.session.execute(sql)
    for row in result:
        print(row)
    return jsonify(result.fetchall())

@api_silo_blueprint.route('/<int:silo_id>/docs', methods=['GET'])
def count_docs_in_silo(app_id: int, silo_id: int):
    count = SiloService.count_docs_in_silo(silo_id)
    return jsonify(count)


@api_silo_blueprint.route('/<int:silo_id>/docs/index', methods=['POST'])
def index_content(app_id: int, silo_id: int):
    data = request.get_json()
    content = data.get('content')
    metadata = data.get('metadata')
    #TODO: validate metadata
    SiloService.index_content(silo_id, content, metadata)
    return jsonify({"message": "test"})

@api_silo_blueprint.route('/<int:silo_id>/docs/delete', methods=['DELETE'])
def delete_docs_in_collection(app_id: int, silo_id: int):
    data = request.get_json()
    ids = data.get('ids')
    SiloService.delete_docs_in_collection(silo_id, ids)
    return jsonify({"message": "docs deleted"})

@api_silo_blueprint.route('/<int:silo_id>/docs/delete/all', methods=['DELETE'])
def delete_all_docs_in_collection(app_id: int, silo_id: int):
    SiloService.delete_collection(silo_id)
    return jsonify({"message": "docs deleted"})

@api_silo_blueprint.route('/<int:silo_id>/docs/find', methods=['POST'])
def find_docs_in_collection(app_id: int, silo_id: int):
    data = request.get_json()
    query = data.get('query')
    filter_metadata = data.get('filter_metadata')
    docs = SiloService.find_docs_in_collection(silo_id, query, filter_metadata)
    
    docs_dict = [{"page_content": doc.page_content, "metadata": doc.metadata} for doc in docs]
    
    return jsonify(docs_dict)


