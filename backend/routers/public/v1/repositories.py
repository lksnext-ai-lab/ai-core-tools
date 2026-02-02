from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
# Import Pydantic models and auth
from .schemas import RepositoriesResponseSchema, RepositoryResponseSchema, CreateRepositoryRequestSchema, SiloSearchSchema, DocsResponseSchema
from .auth import get_api_key_auth, validate_api_key_for_app

# Import services and database
from services.silo_service import SiloService
from db.database import get_db

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

repositories_router = APIRouter()

#REPOSITORY ENDPOINTS

@repositories_router.get("/",
                        summary="Get all repos in app",
                        tags=["Repositories"],
                        response_model=RepositoriesResponseSchema)
async def get_all_repos(
    app_id: int,
    api_key: str = Depends(get_api_key_auth)
):
    """Get all repositories in the specified app."""
    # Validate API key for this app
    auth = validate_api_key_for_app(app_id, api_key)
    
    # TODO: Implement repository listing
    return RepositoriesResponseSchema(repositories=[])

@repositories_router.get("/{repo_id}",
                        summary="Get repo by id",
                        tags=["Repositories"],
                        response_model=RepositoryResponseSchema)
async def get_repo_by_id(
    app_id: int,
    repo_id: int,
    api_key: str = Depends(get_api_key_auth)
):
    """Get a specific repository by ID."""
    # Validate API key for this app
    auth = validate_api_key_for_app(app_id, api_key)
    
    # TODO: Implement repository retrieval
    raise HTTPException(status_code=404, detail="Repository not found")

@repositories_router.post("/",
                         summary="Create repo",
                         tags=["Repositories"],
                         response_model=RepositoryResponseSchema,
                         status_code=201)
async def create_repo(
    app_id: int,
    request: CreateRepositoryRequestSchema,
    api_key: str = Depends(get_api_key_auth)
):
    """Create a new repository."""
    # Validate API key for this app
    auth = validate_api_key_for_app(app_id, api_key)
    
    # TODO: Implement repository creation
    raise HTTPException(status_code=501, detail="Repository creation not implemented")

@repositories_router.post("/{repo_id}/docs/find",
                         summary="Find docs in repository",
                         tags=["Repositories"],
                         response_model=DocsResponseSchema)
async def find_docs_in_repository(
    app_id: int,
    repo_id: int,
    request: SiloSearchSchema,
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """Find documents in a repository's silo collection.
    
    This endpoint allows searching by repository ID instead of needing to know the silo ID.
    """
    # Validate API key for this app
    validate_api_key_for_app(app_id, api_key)
    
    try:
        # Get the repository to find its silo
        from models.repository import Repository
        repository = db.query(Repository).filter(
            Repository.id == repo_id,
            Repository.app_id == app_id
        ).first()
        
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        if not repository.silo_id:
            raise HTTPException(status_code=400, detail="Repository does not have an associated silo")
        
        # Delegate to existing silo search logic
        query = request.query if request.query else " "
        docs = SiloService.find_docs_in_collection(
            silo_id=repository.silo_id,
            query=query,
            filter_metadata=request.filter_metadata,
            db=db
        )
        
        doc_schemas = []
        for doc in docs:
            # Try to get ID from document object first, then from metadata
            doc_id = getattr(doc, 'id', None) or doc.metadata.get("_id") or doc.metadata.get("id") or ""
            doc_schemas.append({
                "page_content": doc.page_content,
                "metadata": {**doc.metadata, "id": str(doc_id) if doc_id else ""}
            })
        
        return DocsResponseSchema(docs=doc_schemas)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding documents in repository: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error finding documents: {str(e)}") 