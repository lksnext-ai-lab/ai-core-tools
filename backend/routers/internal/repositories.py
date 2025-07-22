from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import List, Optional

# Import services
from services.repository_service import RepositoryService
from services.resource_service import ResourceService

# Import schemas and auth
from .schemas import *
from .auth import get_current_user

repositories_router = APIRouter()

# ==================== REPOSITORY MANAGEMENT ====================

@repositories_router.get("/", 
                         summary="List repositories",
                         tags=["Repositories"],
                         response_model=List[RepositoryListItemSchema])
async def list_repositories(app_id: int, current_user: dict = Depends(get_current_user)):
    """
    List all repositories for a specific app.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    # Get repositories using direct database query for now
    from db.session import SessionLocal
    from models.repository import Repository
    
    session = SessionLocal()
    try:
        repositories = session.query(Repository).filter(Repository.app_id == app_id).all()
        
        result = []
        for repo in repositories:
            # Get resource count
            resource_count = len(repo.resources) if repo.resources else 0
            
            result.append(RepositoryListItemSchema(
                repository_id=repo.repository_id,
                name=repo.name,
                created_at=repo.create_date,
                resource_count=resource_count
            ))
        
        return result
    finally:
        session.close()


@repositories_router.get("/{repository_id}",
                        summary="Get repository details",
                        tags=["Repositories"],
                        response_model=RepositoryDetailSchema)
async def get_repository(app_id: int, repository_id: int, current_user: dict = Depends(get_current_user)):
    """
    Get detailed information about a specific repository including its resources.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    from db.session import SessionLocal
    from models.repository import Repository
    from models.resource import Resource
    
    session = SessionLocal()
    try:
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
        repo = session.query(Repository).filter(Repository.repository_id == repository_id).first()
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )
        
        # Get resources
        resources = []
        if repo.resources:
            for resource in repo.resources:
                resources.append({
                    "resource_id": resource.resource_id,
                    "name": resource.name,
                    "file_type": resource.type,  # Database column is 'type', not 'file_type'
                    "created_at": resource.create_date
                })
        
        # Get embedding services for form data - simplified
        from models.embedding_service import EmbeddingService
        embedding_services_query = session.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).all()
        embedding_services = [{"service_id": s.service_id, "name": s.name} for s in embedding_services_query]
        
        return RepositoryDetailSchema(
            repository_id=repo.repository_id,
            name=repo.name,
            created_at=repo.create_date,
            resources=resources,
            embedding_services=embedding_services
        )
        
    finally:
        session.close()


@repositories_router.post("/{repository_id}",
                         summary="Create or update repository",
                         tags=["Repositories"],
                         response_model=RepositoryDetailSchema)
async def create_or_update_repository(
    app_id: int,
    repository_id: int,
    repo_data: CreateUpdateRepositorySchema,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new repository or update an existing one.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    # TODO: Use RepositoryService once it's properly implemented
    
    from db.session import SessionLocal
    from models.repository import Repository
    from datetime import datetime
    
    session = SessionLocal()
    try:
        if repository_id == 0:
            # Create new repository
            repo = Repository()
            repo.app_id = app_id
            repo.create_date = datetime.now()
        else:
            # Update existing repository
            repo = session.query(Repository).filter(Repository.repository_id == repository_id).first()
            if not repo:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Repository not found"
                )
        
        # Update repository data
        repo.name = repo_data.name
        
        session.add(repo)
        session.commit()
        session.refresh(repo)
        
        # Return updated repository (reuse the GET logic)
        return await get_repository(app_id, repo.repository_id, current_user)
        
    finally:
        session.close()


@repositories_router.delete("/{repository_id}",
                           summary="Delete repository",
                           tags=["Repositories"])
async def delete_repository(app_id: int, repository_id: int, current_user: dict = Depends(get_current_user)):
    """
    Delete a repository and all its resources.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    # TODO: Use RepositoryService once it's properly implemented
    
    from db.session import SessionLocal
    from models.repository import Repository
    
    session = SessionLocal()
    try:
        repo = session.query(Repository).filter(Repository.repository_id == repository_id).first()
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )
        
        # Delete repository (cascading delete should handle resources)
        session.delete(repo)
        session.commit()
        
        return {"message": "Repository deleted successfully"}
        
    finally:
        session.close()


# ==================== RESOURCE MANAGEMENT ====================

@repositories_router.post("/{repository_id}/resources",
                         summary="Upload resources",
                         tags=["Resources"])
async def upload_resources(
    app_id: int,
    repository_id: int,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload multiple resources to a repository.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    # TODO: Implement actual file upload and processing logic
    
    # For now, return a placeholder response
    uploaded_files = []
    for file in files:
        uploaded_files.append({
            "filename": file.filename,
            "content_type": file.content_type,
            "size": file.size if hasattr(file, 'size') else 0
        })
    
    return {
        "message": f"Uploaded {len(files)} files to repository {repository_id}",
        "files": uploaded_files,
        "note": "File processing not yet implemented - placeholder response"
    }


@repositories_router.delete("/{repository_id}/resources/{resource_id}",
                           summary="Delete resource",
                           tags=["Resources"])
async def delete_resource(
    app_id: int,
    repository_id: int,
    resource_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a specific resource from a repository.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    # TODO: Use ResourceService once it's properly implemented
    
    from db.session import SessionLocal
    from models.resource import Resource
    
    session = SessionLocal()
    try:
        resource = session.query(Resource).filter(Resource.resource_id == resource_id).first()
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
        
        session.delete(resource)
        session.commit()
        
        return {"message": "Resource deleted successfully"}
        
    finally:
        session.close() 