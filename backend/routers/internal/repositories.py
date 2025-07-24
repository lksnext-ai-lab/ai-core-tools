from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from typing import List, Optional
import os
import logging

# Import services
from services.repository_service import RepositoryService
from services.resource_service import ResourceService

# Import schemas and auth
from .schemas import *
from routers.auth import verify_jwt_token

# Set up logging
logger = logging.getLogger(__name__)

repositories_router = APIRouter()

# Debug log when router is loaded
logger.info("Repositories router loaded successfully")

# ==================== AUTHENTICATION HELPER ====================

async def get_current_user(request: Request):
    """
    Get current authenticated user using Google OAuth JWT tokens.
    
    Args:
        request: FastAPI request object
        
    Returns:
        dict: User information from JWT token
        
    Raises:
        HTTPException: If authentication fails
    """
    # Get token from Authorization header
    auth_header = request.headers.get('Authorization')
    logger.info(f"Auth header received: {auth_header[:20] if auth_header else 'None'}...")
    
    if not auth_header:
        logger.error("No Authorization header found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide Authorization header with Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not auth_header.startswith('Bearer '):
        logger.error(f"Invalid Authorization header format: {auth_header[:50]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Use 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = auth_header.split(' ')[1]
    logger.info(f"Token extracted: {token[:20]}...")
    
    # Verify token using Google OAuth system
    payload = verify_jwt_token(token)
    if not payload:
        logger.error("Token verification failed - invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info(f"Token verified successfully for user: {payload.get('user_id')}")
    return payload

# ==================== REPOSITORY MANAGEMENT ====================

@repositories_router.get("/", 
                         summary="List repositories",
                         tags=["Repositories"],
                         response_model=List[RepositoryListItemSchema])
async def list_repositories(app_id: int, request: Request):
    """
    List all repositories for a specific app.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    logger.info(f"List repositories called for app_id: {app_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    # Use RepositoryService
    repositories = RepositoryService.get_repositories_by_app_id(app_id)
    
    result = []
    for repo in repositories:
        # Get resource count using a separate query to avoid detached instance issues
        from db.session import SessionLocal
        from models.resource import Resource
        
        session = SessionLocal()
        try:
            resource_count = session.query(Resource).filter(Resource.repository_id == repo.repository_id).count()
        finally:
            session.close()
        
        result.append(RepositoryListItemSchema(
            repository_id=repo.repository_id,
            name=repo.name,
            created_at=repo.create_date,
            resource_count=resource_count
        ))
    
    return result


@repositories_router.get("/{repository_id}",
                        summary="Get repository details",
                        tags=["Repositories"],
                        response_model=RepositoryDetailSchema)
async def get_repository(app_id: int, repository_id: int, request: Request):
    """
    Get detailed information about a specific repository including its resources.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    if repository_id == 0:
        # New repository
        return RepositoryDetailSchema(
            repository_id=0,
            name="",
            created_at=None,
            resources=[],
            # Form data - simplified
            embedding_services=[]
        )
    
    # Existing repository
    repo = RepositoryService.get_repository(repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found"
        )
    
    # Get resources using a separate query to avoid detached instance issues
    from db.session import SessionLocal
    from models.resource import Resource
    
    session = SessionLocal()
    try:
        resources_query = session.query(Resource).filter(Resource.repository_id == repository_id).all()
        resources = []
        for resource in resources_query:
            resources.append({
                "resource_id": resource.resource_id,
                "name": resource.name,
                "file_type": resource.type or "unknown",  # Provide default value if type is None
                "created_at": resource.create_date
            })
    finally:
        session.close()
    
    # Get embedding services for form data - simplified
    from db.session import SessionLocal
    from models.embedding_service import EmbeddingService
    from models.repository import Repository
    
    session = SessionLocal()
    try:
        embedding_services_query = session.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).all()
        embedding_services = [{"service_id": s.service_id, "name": s.name} for s in embedding_services_query]
        
        # Get the current embedding service ID from the repository's silo
        # Load repository with relationships within the session to avoid detached instance issues
        repo_with_relations = session.query(Repository).filter(Repository.repository_id == repository_id).first()
        embedding_service_id = None
        if repo_with_relations and repo_with_relations.silo and repo_with_relations.silo.embedding_service:
            embedding_service_id = repo_with_relations.silo.embedding_service.service_id
    finally:
        session.close()
    
    return RepositoryDetailSchema(
        repository_id=repo.repository_id,
        name=repo.name,
        created_at=repo.create_date,
        resources=resources,
        embedding_services=embedding_services,
        embedding_service_id=embedding_service_id
    )


@repositories_router.post("/{repository_id}",
                         summary="Create or update repository",
                         tags=["Repositories"],
                         response_model=RepositoryDetailSchema)
async def create_or_update_repository(
    app_id: int,
    repository_id: int,
    repo_data: CreateUpdateRepositorySchema,
    request: Request
):
    """
    Create a new repository or update an existing one.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    from models.repository import Repository
    from datetime import datetime
    
    if repository_id == 0:
        # Create new repository
        repo = Repository()
        repo.app_id = app_id
        repo.name = repo_data.name
        repo.create_date = datetime.now()
        
        # Use RepositoryService to create repository with silo
        repo = RepositoryService.create_repository(repo, repo_data.embedding_service_id)
    else:
        # Update existing repository
        repo = RepositoryService.get_repository(repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )
        
        # Update repository data
        repo.name = repo_data.name
        repo = RepositoryService.update_repository(repo, repo_data.embedding_service_id)
    
    # Return updated repository (reuse the GET logic)
    return await get_repository(app_id, repo.repository_id, request)


@repositories_router.delete("/{repository_id}",
                           summary="Delete repository",
                           tags=["Repositories"])
async def delete_repository(app_id: int, repository_id: int, request: Request):
    """
    Delete a repository and all its resources.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    repo = RepositoryService.get_repository(repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found"
        )
    
    # Use RepositoryService to delete repository
    RepositoryService.delete_repository(repo)
    
    return {"message": "Repository deleted successfully"}


# ==================== RESOURCE MANAGEMENT ====================

@repositories_router.post("/{repository_id}/resources",
                         summary="Upload resources",
                         tags=["Resources"])
async def upload_resources(
    app_id: int,
    repository_id: int,
    request: Request,
    files: List[UploadFile] = File(...)
):
    """
    Upload multiple resources to a repository.
    """
    logger.info(f"Upload resources endpoint called - app_id: {app_id}, repository_id: {repository_id}, files_count: {len(files)}")
    
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Authentication successful for user: {user_id}")
    
    # TODO: Add app access validation
    
    if not files:
        logger.warning("No files provided in upload request")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided"
        )
    
    # Validate repository exists
    from db.session import SessionLocal
    from models.repository import Repository
    
    session = SessionLocal()
    try:
        repo = session.query(Repository).filter(Repository.repository_id == repository_id).first()
        if not repo:
            logger.error(f"Repository {repository_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )
        
        logger.info(f"Repository {repository_id} found, processing {len(files)} files")
        
        # Use ResourceService to process files
        from services.resource_service import ResourceService
        
        # Process files directly using ResourceService
        created_resources, failed_files = ResourceService.create_multiple_resources(
            files, repository_id
        )
        
        logger.info(f"Upload completed - {len(created_resources)} resources created, {len(failed_files)} failed")
        
        return {
            "message": f"Successfully uploaded {len(created_resources)} files to repository {repository_id}",
            "created_resources": [
                {
                    "resource_id": r.resource_id,
                    "name": r.name,
                    "file_type": r.type or "unknown",
                    "created_at": r.create_date
                } for r in created_resources
            ],
            "failed_files": failed_files
        }
        
    finally:
        session.close()


@repositories_router.delete("/{repository_id}/resources/{resource_id}",
                           summary="Delete resource",
                           tags=["Resources"])
async def delete_resource(
    app_id: int,
    repository_id: int,
    resource_id: int,
    request: Request
):
    """
    Delete a specific resource from a repository.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    # Use ResourceService to delete resource
    success = ResourceService.delete_resource(resource_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found or could not be deleted"
        )
    
    return {"message": "Resource deleted successfully"}


@repositories_router.get("/{repository_id}/resources/{resource_id}/download",
                        summary="Download resource",
                        tags=["Resources"])
async def download_resource(
    app_id: int,
    repository_id: int,
    resource_id: int,
    request: Request
):
    """
    Download a specific resource from a repository.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    logger.info(f"Download request - app_id: {app_id}, repository_id: {repository_id}, resource_id: {resource_id}, user_id: {user_id}")
    
    # TODO: Add app access validation
    
    # Get resource and file path
    resource = ResourceService.get_resource(resource_id)
    if not resource:
        logger.error(f"Resource {resource_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )
    
    logger.info(f"Resource found: {resource.name}, uri: {resource.uri}, repository_id: {resource.repository_id}")
    
    file_path = ResourceService.get_resource_file_path(resource_id)
    logger.info(f"File path: {file_path}")
    
    if not file_path:
        logger.error(f"No file path returned for resource {resource_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File path not found"
        )
    
    if not os.path.exists(file_path):
        logger.error(f"File does not exist at path: {file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk"
        )
    
    logger.info(f"File exists, returning FileResponse for: {file_path}")
    
    # Return file for download
    from fastapi.responses import FileResponse
    return FileResponse(
        path=file_path,
        filename=resource.uri,
        media_type='application/octet-stream'
    ) 