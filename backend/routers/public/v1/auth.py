import hashlib

from fastapi import HTTPException, Depends, status, Request
from fastapi.security.api_key import APIKeyHeader
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional, Callable
from pydantic import BaseModel

from db.database import SessionLocal
from services.public_auth_service import PublicAuthService
from services.agent_service import AgentService
from services.repository_service import RepositoryService
from services.resource_service import ResourceService
from services.silo_service import SiloService
from repositories.media_repository import MediaRepository

# API Key authentication using header
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)
public_auth_service = PublicAuthService()

class APIKeyAuth(BaseModel):
    """API Key authentication result"""
    app_id: int
    api_key: str
    key_id: int

def create_api_key_dependency(app_id: int) -> Callable:
    """
    Create an API key dependency for a specific app_id.
    This is a dependency factory that returns a dependency function.
    """
    def get_api_key_auth(api_key: Optional[str] = Depends(api_key_header)) -> APIKeyAuth:
        """
        Authenticate API requests using API key.
        
        Args:
            api_key: The API key from the X-API-KEY header
            
        Returns:
            APIKeyAuth object with authentication details
            
        Raises:
            HTTPException: If authentication fails
        """
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required. Please provide X-API-KEY header."
            )
        
        session = SessionLocal()
        try:
            api_key_obj = public_auth_service.validate_api_key_for_app(session, app_id, api_key)
            
            return APIKeyAuth(
                app_id=app_id,
                api_key=api_key,
                key_id=api_key_obj.key_id
            )
        
        finally:
            session.close()
    
    return get_api_key_auth

# Simple function for when we have app_id available in the endpoint
def get_api_key_auth(api_key: Optional[str] = Depends(api_key_header)):
    """
    Simple API key authentication that returns the key without app validation.
    App validation happens in the endpoint logic.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Please provide X-API-KEY header."
        )
    return api_key

bearer_scheme = HTTPBearer(auto_error=False)

def get_openai_api_key_auth(
    api_key_header_val: Optional[str] = Depends(api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> str:
    """Auth dependency specifically for OpenAI endpoints, supporting Bearer tokens."""
    # Try Bearer token first
    if bearer and bearer.credentials:
        return bearer.credentials
    # Try X-API-KEY header as fallback
    if api_key_header_val:
        return api_key_header_val
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="API key required. Please provide Authorization: Bearer <API_KEY>."
    )

def validate_api_key_for_app(app_id: int, api_key: str, db: Session = None) -> APIKeyAuth:
    """
    Validate API key for a specific app.

    Args:
        app_id: The app ID to validate against
        api_key: The API key to validate
        db: Optional database session. If provided, reuses it instead of creating a new one.

    Returns:
        APIKeyAuth object with authentication details

    Raises:
        HTTPException: If authentication fails
    """
    if db is not None:
        api_key_obj = public_auth_service.validate_api_key_for_app(db, app_id, api_key)
        return APIKeyAuth(
            app_id=app_id,
            api_key=api_key,
            key_id=api_key_obj.key_id
        )

    session = SessionLocal()
    try:
        api_key_obj = public_auth_service.validate_api_key_for_app(session, app_id, api_key)

        return APIKeyAuth(
            app_id=app_id,
            api_key=api_key,
            key_id=api_key_obj.key_id
        )

    finally:
        session.close()


def create_api_key_user_context(app_id: int, api_key: str, conversation_id: str = None) -> dict:
    """
    Create user context for API key authentication.
    Uses a hash of the API key as user identifier to maintain session isolation.

    Args:
        app_id: Application ID
        api_key: API key for authentication
        conversation_id: Optional conversation ID
    """
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    context = {
        "user_id": f"apikey_{api_key_hash}",
        "app_id": app_id,
        "oauth": False,
        "api_key": api_key
    }
    if conversation_id is not None:
        context["conversation_id"] = conversation_id
    return context


def validate_agent_ownership(db: Session, agent_id: int, app_id: int):
    """
    Validate that an agent exists and belongs to the specified app.

    Args:
        db: Database session
        agent_id: Agent ID to validate
        app_id: App ID to check ownership against

    Returns:
        The agent object if valid

    Raises:
        HTTPException: 404 if agent not found or doesn't belong to app
    """
    agent_service = AgentService()
    agent = agent_service.get_agent(db, agent_id)
    if not agent or agent.app_id != app_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def validate_repository_ownership(db: Session, repo_id: int, app_id: int):
    """
    Validate that a repository exists and belongs to the specified app.

    Returns:
        The repository object if valid

    Raises:
        HTTPException: 404 if repository not found or doesn't belong to app
    """
    repo = RepositoryService.get_repository(repo_id, db)
    if not repo or repo.app_id != app_id:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


def validate_resource_ownership(db: Session, resource_id: int, repo_id: int):
    """
    Validate that a resource exists and belongs to the specified repository.

    Returns:
        The resource object if valid

    Raises:
        HTTPException: 404 if resource not found or doesn't belong to repository
    """
    resource = ResourceService.get_resource(resource_id, db)
    if not resource or resource.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource


def validate_media_ownership(db: Session, media_id: int, repo_id: int):
    """
    Validate that a media item exists and belongs to the specified repository.

    Returns:
        The media object if valid

    Raises:
        HTTPException: 404 if media not found or doesn't belong to repository
    """
    media = MediaRepository.get_by_id(media_id, db)
    if not media or media.repository_id != repo_id:
        raise HTTPException(status_code=404, detail="Media not found")
    return media


def validate_silo_ownership(db: Session, silo_id: int, app_id: int):
    """
    Validate that a silo exists and belongs to the specified app.

    Returns:
        The silo object if valid

    Raises:
        HTTPException: 404 if silo not found or doesn't belong to app
    """
    silo = SiloService.get_silo(silo_id, db)
    if not silo or silo.app_id != app_id:
        raise HTTPException(status_code=404, detail="Silo not found")
    return silo