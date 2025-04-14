from flask import jsonify, request
from flask_openapi3 import APIBlueprint, Tag
from sqlalchemy import text
from model.silo import Silo
from extensions import db
from services.silo_service import SiloService
from api.api_auth import require_auth
from api.pydantic.silos_pydantic import (SiloPath, SiloSearch, SingleDocumentIndex, MultipleDocumentIndex,
                                         DocsResponse, CountResponse, MessageResponse)
from api.pydantic.pydantic import AppPath
from typing import List

silo_tag = Tag(name="Silo", description="Silo description")
security=[{"api_key":[]}]
silo_api = APIBlueprint('silo_api', __name__, url_prefix='/api/silo/app/<int:app_id>/silos', abp_security=security)


@silo_api.get('/<int:silo_id>/docs', summary="count docs in silo", tags=[silo_tag],
              responses={"200": CountResponse})
@require_auth
def count_docs_in_silo(path: SiloPath):
    count = SiloService.count_docs_in_silo(path.silo_id)
    return jsonify({"count": count})

@silo_api.post('/<int:silo_id>/docs/index', summary="index content", tags=[silo_tag],
               responses={"200": MessageResponse})
@require_auth
def index_single_document(path: SiloPath, body: SingleDocumentIndex):
    #data = request.get_json()
    content = body.content
    metadata = body.metadata
    #TODO: validate metadata
    SiloService.index_single_content(path.silo_id, content, metadata)
    return jsonify({"message": "content indexed successfully"})

@silo_api.post('/<int:silo_id>/docs/multiple-index', summary="index multiple documents", tags=[silo_tag],
               responses={"200": MessageResponse})
@require_auth
def index_multiple_document(path: SiloPath, body: MultipleDocumentIndex):
    SiloService.index_multiple_content(path.silo_id, body.documents)
    return jsonify({"message": "documents indexed successfully"})

@silo_api.delete('/<int:silo_id>/docs/delete', summary="delete docs in collection", tags=[silo_tag],
                 responses={"200": MessageResponse})
@require_auth
def delete_docs_in_collection(path: SiloPath):
    data = request.get_json()
    ids = data.get('ids')
    SiloService.delete_docs_in_collection(path.silo_id, ids)
    return jsonify({"message": "docs deleted"})

@silo_api.delete('/<int:silo_id>/docs/delete/all', summary="delete all docs in collection", tags=[silo_tag],
                 responses={"200": MessageResponse})
@require_auth
def delete_all_docs_in_collection(path: SiloPath):
    SiloService.delete_collection(path.silo_id)
    return jsonify({"message": "docs deleted"})

@silo_api.post('/<int:silo_id>/docs/find', summary="find docs in collection", tags=[silo_tag],
               responses={"200": DocsResponse})
@require_auth
def find_docs_in_collection(path: SiloPath, body: SiloSearch):
    query = body.query
    filter_metadata = body.filter_metadata
    docs = SiloService.find_docs_in_collection(path.silo_id, query, filter_metadata)
    
    return {"docs":[{"page_content": doc.page_content, "metadata": doc.metadata} for doc in docs]}


@silo_api.get('/test', summary="get silos", tags=[silo_tag])
@require_auth
def get_silos(path: AppPath):
    silos = db.session.query(Silo).filter(Silo.app_id == path.app_id).all()
    sql = text("SELECT * FROM langchain_pg_embedding WHERE cmetadata @> '{\"topic\": \"animals\"}';")
    result = db.session.execute(sql)
    for row in result:
        print(row)
    return jsonify(result.fetchall())
