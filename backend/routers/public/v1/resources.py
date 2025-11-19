from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import List, Optional

from services.resource_service import ResourceService

# Import Pydantic models and auth
from .schemas import ResourceListResponseSchema, MultipleResourceResponseSchema, MessageResponseSchema
from .auth import get_api_key_auth, validate_api_key_for_app

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

resources_router = APIRouter()

#RESOURCE ENDPOINTS

@resources_router.get("/{repo_id}",
                     summary="Get all resources in repo",
                     tags=["Resources"])
async def get_all_resources(
    app_id: int,
    repo_id: int,
    api_key: str = Depends(get_api_key_auth)
):
    """Get all resources in a repository."""
    # Validate API key for this app
    auth = validate_api_key_for_app(app_id, api_key)
    
    # TODO: Implement resource listing
    return ResourceListResponseSchema(resources=[])

@resources_router.post("/{repo_id}",
                      summary="Create multiple resources",
                      tags=["Resources"],
                      response_model=MultipleResourceResponseSchema,
                      status_code=201)
async def create_multiple_resources(
    app_id: int,
    repo_id: int,
    files: List[UploadFile] = File(...),
    folder_id: Optional[int] = Form(None),
    api_key: str = Depends(get_api_key_auth)
):
    """Create multiple resources from uploaded files. Optionally specify folder_id to upload to a specific folder."""
    # Validate API key for this app
    auth = validate_api_key_for_app(app_id, api_key)
    
    # Get database session
    from db.database import get_db
    db = next(get_db())
    
    try:
        # Use ResourceService to handle the business logic
        result = ResourceService.upload_resources_to_repository(
            app_id=app_id,
            repository_id=repo_id,
            files=files,
            db=db,
            folder_id=folder_id
        )
        
        return MultipleResourceResponseSchema(
            message=result.get("message", "Resources created successfully"),
            created_resources=result.get("created_resources", []),
            failed_files=result.get("failed_files", [])
        )
    except Exception as e:
        logger.error(f"Error creating resources: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create resources: {str(e)}"
        )
    finally:
        db.close()

@resources_router.delete("/{repo_id}/{resource_id}",
                        summary="Delete resource",
                        tags=["Resources"],
                        response_model=MessageResponseSchema)
async def delete_resource(
    app_id: int,
    repo_id: int,
    resource_id: int,
    api_key: str = Depends(get_api_key_auth)
):
    """Delete a resource from a repository."""
    # Validate API key for this app
    auth = validate_api_key_for_app(app_id, api_key)
    
    # TODO: Implement resource deletion
    return MessageResponseSchema(message="Resource deleted successfully") 