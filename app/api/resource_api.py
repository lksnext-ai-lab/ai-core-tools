from typing import List
from flask import jsonify, request
from flask_openapi3 import APIBlueprint, Tag
from app.api.api_auth import require_auth
from app.api.pydantic.repos_pydantic import RepoPath, CreateRepositoryRequest
from app.services.repository_service import RepositoryService 
from app.api.pydantic.pydantic import AppPath
from app.model.repository import Repository
from app.model.resource import Resource
from app.api.pydantic.repos_pydantic import RepositorySchema
from app.services.resource_service import ResourceService
from app.api.pydantic.resources_pydantic import ResourceSchema, CreateResourceForm, ResourcePath

resource_tag = Tag(name="Resource", description="Resource operations")

resource_api = APIBlueprint('resource_api', __name__, url_prefix='/api/resource/app/<int:app_id>/repos/<int:repo_id>')


@resource_api.get('/', 
    summary="Get all resources in repo", 
    tags=[resource_tag]
)
@require_auth
def get_all_resources(path: RepoPath) -> List[ResourceSchema]:
    resources = ResourceService.get_resources_by_repo_id(path.repo_id)
    return jsonify([ResourceSchema.model_validate(resource).model_dump() for resource in resources])

@resource_api.post('/', 
    summary="Create resource", 
    tags=[resource_tag]
)
@require_auth
def create_resource(path: RepoPath, form: CreateResourceForm) -> ResourceSchema:
    resource = Resource()
    resource.name = form.name
    resource.uri = form.file.filename
    resource.type = form.type
    resource.status = form.status
    resource.repository_id = path.repo_id
    resource = ResourceService.create_resource(form.file, form.name, resource)
    return jsonify({"message": "Resource created successfully", "resource": ResourceSchema.model_validate(resource).model_dump()}), 201

@resource_api.delete('/<int:resource_id>', 
    summary="Delete resource", 
    tags=[resource_tag]
)
@require_auth
def delete_resource(path: ResourcePath):
    ResourceService.delete_resource(path.resource_id)
    return jsonify({"message": "Resource deleted successfully"}), 200