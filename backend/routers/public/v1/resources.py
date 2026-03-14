from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from typing import List, Optional
from sqlalchemy.orm import Session

from services.resource_service import ResourceService

from .schemas import (
    ResourceListResponseSchema,
    ResourceSchema,
    MultipleResourceResponseSchema,
    MessageResponseSchema,
)
from .auth import (
    get_api_key_auth,
    validate_api_key_for_app,
    validate_repository_ownership,
    validate_resource_ownership,
    create_api_key_user_context,
)

from db.database import get_db

from utils.logger import get_logger

logger = get_logger(__name__)

resources_router = APIRouter()


# ==================== RESOURCE ENDPOINTS ====================


@resources_router.get(
    "/{repo_id}",
    summary="Get all resources in repository",
    tags=["Resources"],
    response_model=ResourceListResponseSchema,
)
async def get_all_resources(
    app_id: int,
    repo_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """Get all resources in a repository."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_repository_ownership(db, repo_id, app_id)

    try:
        resources = ResourceService.get_resources_by_repo_id(repo_id, db)
        return ResourceListResponseSchema(
            resources=[ResourceSchema.model_validate(r) for r in resources]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing resources: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list resources",
        )


@resources_router.post(
    "/{repo_id}",
    summary="Upload resources to repository",
    tags=["Resources"],
    response_model=MultipleResourceResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_multiple_resources(
    app_id: int,
    repo_id: int,
    files: List[UploadFile] = File(...),
    folder_id: Optional[int] = Form(None),
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """Upload multiple resources to a repository. Optionally specify folder_id to upload to a specific folder."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_repository_ownership(db, repo_id, app_id)

    try:
        result = ResourceService.upload_resources_to_repository(
            app_id=app_id,
            repository_id=repo_id,
            files=files,
            db=db,
            folder_id=folder_id,
        )

        return MultipleResourceResponseSchema(
            message=result.get("message", "Resources created successfully"),
            created_resources=result.get("created_resources", []),
            failed_files=result.get("failed_files", []),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating resources: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create resources",
        )


@resources_router.delete(
    "/{repo_id}/{resource_id}",
    summary="Delete resource",
    tags=["Resources"],
    response_model=MessageResponseSchema,
)
async def delete_resource(
    app_id: int,
    repo_id: int,
    resource_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """Delete a resource from a repository."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_repository_ownership(db, repo_id, app_id)
    validate_resource_ownership(db, resource_id, repo_id)

    try:
        ResourceService.delete_resource_from_repository(
            app_id=app_id,
            repository_id=repo_id,
            resource_id=resource_id,
            db=db,
        )
        logger.info(f"Resource {resource_id} deleted via public API")
        return MessageResponseSchema(message="Resource deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting resource: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete resource",
        )


@resources_router.get(
    "/{repo_id}/resources/{resource_id}/download",
    summary="Download resource",
    tags=["Resources"],
)
async def download_resource(
    app_id: int,
    repo_id: int,
    resource_id: int,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db),
):
    """Download a resource file from a repository."""
    validate_api_key_for_app(app_id, api_key, db)
    validate_repository_ownership(db, repo_id, app_id)
    validate_resource_ownership(db, resource_id, repo_id)

    try:
        user_context = create_api_key_user_context(app_id, api_key)
        file_path, filename = ResourceService.download_resource_from_repository(
            app_id=app_id,
            repository_id=repo_id,
            resource_id=resource_id,
            user_id=user_context["user_id"],
            db=db,
        )
        return FileResponse(path=file_path, filename=filename)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading resource: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download resource",
        )
