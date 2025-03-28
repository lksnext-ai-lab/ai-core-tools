from flask import jsonify
from flask_openapi3 import APIBlueprint, Tag
from api.api_auth import require_auth
from api.pydantic.repos_pydantic import (
    RepoPath, CreateRepositoryRequest, RepositorySchema,
    RepositoriesResponse, RepositoryResponse
)
from services.repository_service import RepositoryService 
from api.pydantic.pydantic import AppPath
from model.repository import Repository

repo_tag = Tag(name="Repository", description="Repository operations")
security=[{"api_key":[]}]
repo_api = APIBlueprint('repo_api', __name__, url_prefix='/api/repo/app/<int:app_id>/repos', abp_security=security)


@repo_api.get('/', 
    summary="Get all repos in app", 
    tags=[repo_tag],
    responses={"200": RepositoriesResponse}
)
@require_auth
def get_all_repos(path: AppPath):
    repos = RepositoryService.get_repositories_by_app_id(path.app_id)
    return jsonify({"repositories": [RepositorySchema.model_validate(repo).model_dump() for repo in repos]})


@repo_api.get('/<int:repo_id>', 
    summary="Get repo by id", 
    tags=[repo_tag],
    responses={"200": RepositoryResponse}
)
@require_auth
def get_repo_by_id(path: RepoPath) -> RepositorySchema:
    repo = RepositoryService.get_repository(path.repo_id)
    return jsonify({"repository": RepositorySchema.model_validate(repo).model_dump()})


@repo_api.post('/', 
    summary="Create repo",  
    tags=[repo_tag],
    responses={"201": RepositoryResponse}
)
@require_auth
def create_repo(path: AppPath, body: CreateRepositoryRequest):
    repository = Repository(
        name=body.name,
        app_id=path.app_id
    )
    repository = RepositoryService.create_repository(repository)
    return jsonify({"repository": RepositorySchema.model_validate(repository).model_dump()})