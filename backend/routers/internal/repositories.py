from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from typing import List, Optional
import os
import logging
from sqlalchemy.orm import Session

# Import services
from services.repository_service import RepositoryService
from services.resource_service import ResourceService

from schemas.repository_schemas import RepositoryListItemSchema, RepositoryDetailSchema, CreateUpdateRepositorySchema, RepositorySearchSchema
from routers.internal.auth_utils import get_current_user_oauth
from routers.controls import enforce_file_size_limit

# Import database dependency
from db.database import get_db

# Set up logging
logger = logging.getLogger(__name__)

repositories_router = APIRouter()

# Debug log when router is loaded
logger.info("Repositories router loaded successfully")



# ==================== REPOSITORY MANAGEMENT ====================

@repositories_router.get("/", 
                         summary="List repositories",
                         tags=["Repositories"],
                         response_model=List[RepositoryListItemSchema])
async def list_repositories(app_id: int, request: Request, db: Session = Depends(get_db)):
    """
    List all repositories for a specific app.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    logger.info(f"List repositories called for app_id: {app_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    # Use RepositoryService for business logic
    return RepositoryService.get_repositories_list(app_id, db)


@repositories_router.get("/{repository_id}",
                        summary="Get repository details",
                        tags=["Repositories"],
                        response_model=RepositoryDetailSchema)
async def get_repository(app_id: int, repository_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific repository including its resources.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    # Use RepositoryService for business logic
    return RepositoryService.get_repository_detail(app_id, repository_id, db)


@repositories_router.post("/{repository_id}",
                         summary="Create or update repository",
                         tags=["Repositories"],
                         response_model=RepositoryDetailSchema)
async def create_or_update_repository(
    app_id: int,
    repository_id: int,
    repo_data: CreateUpdateRepositorySchema,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Create a new repository or update an existing one.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    # Use RepositoryService for business logic
    repo = RepositoryService.create_or_update_repository_router(app_id, repository_id, repo_data, db)
    
    # Return updated repository (reuse the GET logic)
    return RepositoryService.get_repository_detail(app_id, repo.repository_id, db)


@repositories_router.delete("/{repository_id}",
                           summary="Delete repository",
                           tags=["Repositories"])
async def delete_repository(app_id: int, repository_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Delete a repository and all its resources.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    # Use RepositoryService for business logic
    RepositoryService.delete_repository_router(repository_id, db)
    
    return {"message": "Repository deleted successfully"}


# ==================== RESOURCE MANAGEMENT ====================

@repositories_router.post("/{repository_id}/resources",
                         summary="Upload resources",
                         tags=["Resources"])
async def upload_resources(
    app_id: int,
    repository_id: int,
    request: Request,
    files: List[UploadFile] = File(...),
    folder_id: Optional[int] = Form(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(enforce_file_size_limit)
):
    """
    Upload multiple resources to a repository.
    Optionally specify a folder_id to upload files to a specific folder.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Upload resources endpoint called - app_id: {app_id}, repository_id: {repository_id}, files_count: {len(files)}, folder_id: {folder_id} (type: {type(folder_id)}), user_id: {user_id}")
    
    # TODO: Add app access validation
    
    # Use ResourceService to handle the business logic
    result = ResourceService.upload_resources_to_repository(
        app_id=app_id,
        repository_id=repository_id,
        files=files,
        db=db,
        folder_id=folder_id
    )
    
    return result


@repositories_router.post("/{repository_id}/resources/{resource_id}/move",
                         summary="Move resource to different folder",
                         tags=["Resources"])
async def move_resource(
    app_id: int,
    repository_id: int,
    resource_id: int,
    request: Request,
    new_folder_id: Optional[int] = Form(default=None),
    db: Session = Depends(get_db)
):
    """
    Move a resource to a different folder within the same repository.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Move resource endpoint called - app_id: {app_id}, repository_id: {repository_id}, resource_id: {resource_id}, new_folder_id: {new_folder_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    # Use ResourceService to handle the business logic
    result = ResourceService.move_resource_to_folder(
        resource_id=resource_id,
        repository_id=repository_id,
        new_folder_id=new_folder_id,
        db=db
    )
    
    return result


@repositories_router.delete("/{repository_id}/resources/{resource_id}",
                           summary="Delete resource",
                           tags=["Resources"])
async def delete_resource(
    app_id: int,
    repository_id: int,
    resource_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Delete a specific resource from a repository.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Delete resource endpoint called - app_id: {app_id}, repository_id: {repository_id}, resource_id: {resource_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    # Use ResourceService to handle the business logic
    result = ResourceService.delete_resource_from_repository(
        app_id=app_id,
        repository_id=repository_id,
        resource_id=resource_id,
        db=db
    )
    
    return result


@repositories_router.get("/{repository_id}/resources/{resource_id}/download",
                        summary="Download resource",
                        tags=["Resources"])
async def download_resource(
    app_id: int,
    repository_id: int,
    resource_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Download a specific resource from a repository.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Download resource endpoint called - app_id: {app_id}, repository_id: {repository_id}, resource_id: {resource_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    # Use ResourceService to handle the business logic
    file_path, filename = ResourceService.download_resource_from_repository(
        app_id=app_id,
        repository_id=repository_id,
        resource_id=resource_id,
        user_id=user_id,
        db=db
    )
    
    # Return file for download
    from fastapi.responses import FileResponse
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )


# ==================== REPOSITORY SEARCH ====================

@repositories_router.post("/{repository_id}/search",
                         summary="Search documents in repository",
                         tags=["Repositories", "Search"])
async def search_repository_documents(
    app_id: int,
    repository_id: int,
    search_query: RepositorySearchSchema,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Search for documents in a repository using semantic search with optional metadata filtering.
    This leverages the repository's associated silo for searching.
    """
    current_user = await get_current_user_oauth(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Repository search request - app_id: {app_id}, repository_id: {repository_id}, user_id: {user_id}")
    logger.info(f"Search query: {search_query.query}, limit: {search_query.limit}, filter_metadata: {search_query.filter_metadata}")
    
    # TODO: Add app access validation
    
    try:
        # Use RepositoryService to handle the search
        result = RepositoryService.search_repository_documents_router(
            repository_id=repository_id,
            query=search_query.query,
            filter_metadata=search_query.filter_metadata,
            limit=search_query.limit or 10,
            db=db
        )
        
        logger.info(f"Repository search completed - found {len(result.get('results', []))} results")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching repository {repository_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching repository: {str(e)}"
        ) 