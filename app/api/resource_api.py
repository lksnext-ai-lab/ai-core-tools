from flask import jsonify, Response, request
from flask_openapi3 import APIBlueprint, Tag
from api.api_auth import require_auth
from api.pydantic.repos_pydantic import RepoPath
from model.resource import Resource
from services.resource_service import ResourceService
from api.pydantic.resources_pydantic import (
    ResourceSchema, CreateMultipleResourcesForm, ResourcePath,
    ResourceListResponse, MultipleResourceResponse, MessageResponse
)

resource_tag = Tag(name="Resource", description="Resource operations")
security=[{"api_key":[]}]
resource_api = APIBlueprint('resource_api', __name__, url_prefix='/api/resource/app/<int:app_id>/repos/<int:repo_id>', abp_security=security)


@resource_api.get('/', 
    summary="Get all resources in repo", 
    tags=[resource_tag],
    responses={"200": ResourceListResponse}
)
@require_auth
def get_all_resources(path: RepoPath) -> Response:
    resources = ResourceService.get_resources_by_repo_id(path.repo_id)
    return jsonify([ResourceSchema.model_validate(resource).model_dump() for resource in resources])

@resource_api.post('/', 
    summary="Create multiple resources", 
    tags=[resource_tag],
    responses={"201": MultipleResourceResponse}
)
@require_auth
def create_multiple_resources(path: RepoPath) -> Response:
    """
    Create multiple resources from uploaded files with optional custom names
    
    Expects form data with:
    - files: List of files to upload
    - custom_names[0], custom_names[1], etc.: Optional custom names for each file (without extension)
    """
    # Get uploaded files
    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({"message": "No files provided"}), 400
    
    # Extract custom names from form data
    custom_names = {}
    for key, value in request.form.items():
        if key.startswith('custom_names[') and key.endswith(']'):
            # Extract index from custom_names[0], custom_names[1], etc.
            index_str = key[len('custom_names['):-1]
            try:
                index = int(index_str)
                if value.strip():  # Only use non-empty custom names
                    custom_names[index] = value.strip()
            except ValueError:
                continue  # Skip invalid indices
    
    try:
        created_resources, failed_files = ResourceService.create_multiple_resources(
            files, path.repo_id, custom_names
        )
        
        # Convert resources to schemas
        resource_schemas = [
            ResourceSchema.model_validate(resource).model_dump() 
            for resource in created_resources
        ]
        
        response_data = {
            "message": f"Successfully processed {len(created_resources)} out of {len(files)} files",
            "created_resources": resource_schemas,
            "failed_files": failed_files
        }
        
        return jsonify(response_data), 201
        
    except Exception as e:
        return jsonify({"message": f"Error processing files: {str(e)}"}), 500

@resource_api.delete('/<int:resource_id>', 
    summary="Delete resource", 
    tags=[resource_tag],
    responses={"200": MessageResponse}
)
@require_auth
def delete_resource(path: ResourcePath):
    ResourceService.delete_resource(path.resource_id)
    return jsonify({"message": "Resource deleted successfully"}), 200