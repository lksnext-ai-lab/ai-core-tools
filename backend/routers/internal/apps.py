from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Tuple
from sqlalchemy.orm import Session
from lks_idprovider.models.auth import AuthContext

# Import database
from db.database import get_db

# Import services
from services.app_service import AppService
from services.app_collaboration_service import AppCollaborationService
from services.rate_limit_service import rate_limit_service

# Import schemas and auth
from schemas.apps_schemas import (
    AppListItemSchema, AppDetailSchema, CreateAppSchema, UpdateAppSchema, AppUsageStatsSchema
)
from schemas.common_schemas import MessageResponseSchema
from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole

# Import nested routers for app-specific resources
from .agents import agents_router
from .silos import silos_router
from .ai_services import ai_services_router
from .api_keys import api_keys_router
from .domains import domains_router
from .embedding_services import embedding_services_router
from .mcp_configs import mcp_configs_router
from .ocr import ocr_router
from .output_parsers import output_parsers_router
from .repositories import repositories_router
from .folders import folders_router
from .mcp_servers import mcp_servers_router
from .skills import skills_router

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

apps_router = APIRouter()

# Default value used when an app's agent_rate_limit is not set
DEFAULT_AGENT_RATE_LIMIT = 0
DEFAULT_MAX_FILE_SIZE_MB = 0

# Error messages
APP_NOT_FOUND_MSG = "App not found"

# Include nested routers under apps/{app_id}/
# Based on frontend API calls - all app-specific resources go here
apps_router.include_router(agents_router, prefix="/{app_id}/agents", tags=["Agents"])
apps_router.include_router(silos_router, prefix="/{app_id}/silos", tags=["Silos"])
apps_router.include_router(ai_services_router, prefix="/{app_id}/ai-services", tags=["AI Services"])
apps_router.include_router(api_keys_router, prefix="/{app_id}/api-keys", tags=["API Keys"])
apps_router.include_router(domains_router, prefix="/{app_id}/domains", tags=["Domains"])
apps_router.include_router(embedding_services_router, prefix="/{app_id}/embedding-services", tags=["Embedding Services"])
apps_router.include_router(mcp_configs_router, prefix="/{app_id}/mcp-configs", tags=["MCP Configs"])
apps_router.include_router(ocr_router, prefix="/{app_id}/ocr", tags=["OCR"])
apps_router.include_router(output_parsers_router, prefix="/{app_id}/output-parsers", tags=["Output Parsers"])
apps_router.include_router(repositories_router, prefix="/{app_id}/repositories", tags=["Repositories"])
apps_router.include_router(folders_router, prefix="/{app_id}/repositories/{repository_id}/folders", tags=["Folders"])
apps_router.include_router(mcp_servers_router, prefix="/{app_id}/mcp-servers", tags=["MCP Servers"])
apps_router.include_router(skills_router, prefix="/{app_id}/skills", tags=["Skills"])

#HELPER FUNCTIONS

def get_services(db: Session) -> Tuple[AppService, AppCollaborationService]:
    """
    Helper function to initialize and return app services.
    """
    app_service = AppService(db)
    collaboration_service = AppCollaborationService(db)
    return app_service, collaboration_service

def _safe_get_count(items) -> int:
    """
    Safely get count from a list or collection, returning 0 if None.
    """
    return len(items) if items else 0

def _handle_savepoint_rollback(savepoint, db: Session, app_id: int):
    """
    Handle rolling back a savepoint with proper error handling.
    """
    try:
        savepoint.rollback()
    except Exception as rollback_error:
        logger.error(f"Error rolling back savepoint for app {app_id}: {str(rollback_error)}")
        _handle_transaction_rollback(db, app_id)

def _handle_transaction_rollback(db: Session, app_id: int):
    """
    Handle rolling back the entire transaction with error handling.
    """
    try:
        db.rollback()
    except Exception as rollback_error:
        logger.error(f"Error rolling back transaction for app {app_id}: {str(rollback_error)}")

def _get_entity_counts(app_id: int, db: Session, collaboration_service: AppCollaborationService) -> dict:
    """
    Fetch all entity counts for an app.
    """
    from services.agent_service import AgentService
    from services.repository_service import RepositoryService
    from services.domain_service import DomainService
    from services.silo_service import SiloService
    
    agent_service = AgentService()
    agents = agent_service.get_agents(db, app_id)
    repositories = RepositoryService.get_repositories_by_app_id(app_id, db)
    domains = DomainService.get_domains_by_app_id(app_id, db)
    silos = SiloService.get_silos_by_app_id(app_id, db)
    collaborators = collaboration_service.get_app_collaborators(app_id)
    
    return {
        'agent_count': _safe_get_count(agents),
        'repository_count': _safe_get_count(repositories),
        'domain_count': _safe_get_count(domains),
        'silo_count': _safe_get_count(silos),
        'collaborator_count': _safe_get_count(collaborators)
    }

def _get_empty_counts() -> dict:
    """
    Return a dictionary with all counts set to 0.
    """
    return {
        'agent_count': 0,
        'repository_count': 0,
        'domain_count': 0,
        'silo_count': 0,
        'collaborator_count': 0
    }

def calculate_app_entity_counts(app_id: int, db: Session, collaboration_service: AppCollaborationService) -> dict:
    """
    Calculate entity counts for an app (agents, repositories, domains, silos, collaborators).
    
    Args:
        app_id: The ID of the app
        db: Database session
        collaboration_service: Collaboration service instance
        
    Returns:
        Dictionary with count values for each entity type
    """
    savepoint = None
    try:
        savepoint = db.begin_nested()
        counts = _get_entity_counts(app_id, db, collaboration_service)
        
        if savepoint:
            savepoint.commit()
        return counts
        
    except Exception as e:
        logger.warning(f"Error calculating counts for app {app_id}: {str(e)}")
        
        if savepoint:
            _handle_savepoint_rollback(savepoint, db, app_id)
        else:
            _handle_transaction_rollback(db, app_id)
        
        return _get_empty_counts()


#APP MANAGEMENT

@apps_router.get("/", 
                summary="List user's apps",
                tags=["Apps"],
                response_model=List[AppListItemSchema])
async def list_apps(
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    List all apps that the current user owns or collaborates on.
    """
    user_id = int(auth_context.identity.id)  # Extract DB user_id from enriched context
    
    app_service, collaboration_service = get_services(db)
    
    apps = app_service.get_apps(user_id)
    
    # Convert to schema
    app_list = []
    for app in apps:
        role = collaboration_service.get_user_app_role(user_id, app.app_id) or "owner"
        
        # Calculate entity counts using helper function
        counts = calculate_app_entity_counts(app.app_id, db, collaboration_service)
        
        # Get usage statistics for speedometer
        usage_stats = rate_limit_service.get_app_usage_stats(
            app.app_id, 
            app.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT
        )
        usage_stats_schema = AppUsageStatsSchema(**usage_stats)
        
        # Get owner information
        owner_name = None
        owner_email = None
        if app.owner:
            owner_name = app.owner.name
            owner_email = app.owner.email
        
        app_item = AppListItemSchema(
            app_id=app.app_id,
            name=app.name,
            role=role,
            created_at=app.create_date,
            langsmith_configured=bool(app.langsmith_api_key),
            owner_id=app.owner_id,
            owner_name=owner_name,
            owner_email=owner_email,
            agent_rate_limit=app.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT,
            max_file_size_mb=app.max_file_size_mb or DEFAULT_MAX_FILE_SIZE_MB,
            agent_cors_origins=app.agent_cors_origins,
            usage_stats=usage_stats_schema,
            **counts  # Unpack the counts dictionary
        )
        app_list.append(app_item)
    
    return app_list


@apps_router.get("/{app_id}",
                summary="Get app details",
                tags=["Apps"], 
                response_model=AppDetailSchema)
async def get_app(
    app_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific app.
    """
    user_id = int(auth_context.identity.id)
    
    app_service, collaboration_service = get_services(db)
    
    # Get app and verify access
    app = app_service.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=APP_NOT_FOUND_MSG
        )
    
    if not collaboration_service.can_user_access_app(user_id, app_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this app"
        )
    
    user_role = collaboration_service.get_user_app_role(user_id, app_id)
    
    counts = calculate_app_entity_counts(app_id, db, collaboration_service)
    
    # Get owner information
    owner_email = None
    owner_name = None
    if app.owner:
        owner_email = app.owner.email
        owner_name = app.owner.name
    
    return AppDetailSchema(
        app_id=app.app_id,
        name=app.name,
        langsmith_api_key=app.langsmith_api_key or "",
        user_role=user_role,
        created_at=app.create_date,
        owner_id=app.owner_id,
        owner_email=owner_email,
        owner_name=owner_name,
        agent_rate_limit=app.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT,
        max_file_size_mb=app.max_file_size_mb or DEFAULT_MAX_FILE_SIZE_MB,
        agent_cors_origins=app.agent_cors_origins,
        **counts
    )


@apps_router.post("/",
                 summary="Create new app",
                 tags=["Apps"],
                 response_model=AppDetailSchema,
                 status_code=status.HTTP_201_CREATED)
async def create_app(
    app_data: CreateAppSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Create a new app for the current user.
    """
    user_id = int(auth_context.identity.id)  # Extract DB user_id from enriched context
    
    app_service, _ = get_services(db)
    
    app_dict = {
        'name': app_data.name,
        'owner_id': user_id,
        'langsmith_api_key': app_data.langsmith_api_key,
        'agent_rate_limit': (app_data.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT),
        'max_file_size_mb': (app_data.max_file_size_mb or DEFAULT_MAX_FILE_SIZE_MB),
        'agent_cors_origins': app_data.agent_cors_origins
    }
    
    app = app_service.create_or_update_app(app_dict)
    
    # Get owner information
    owner_email = None
    owner_name = None
    if app.owner:
        owner_email = app.owner.email
        owner_name = app.owner.name
    
    return AppDetailSchema(
        app_id=app.app_id,
        name=app.name,
        langsmith_api_key=app.langsmith_api_key or "",
        user_role="owner",
        created_at=app.create_date,
        owner_id=app.owner_id,
        owner_email=owner_email,
        owner_name=owner_name,
        agent_rate_limit=app.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT,
        max_file_size_mb=app.max_file_size_mb or DEFAULT_MAX_FILE_SIZE_MB,
        agent_cors_origins=app.agent_cors_origins
    )


@apps_router.put("/{app_id}",
                summary="Update app",
                tags=["Apps"],
                response_model=AppDetailSchema)
async def update_app(
    app_id: int,
    app_data: UpdateAppSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Update an existing app. Only owners can update apps.
    """
    user_id = int(auth_context.identity.id)  # Extract DB user_id from enriched context
    
    app_service, collaboration_service = get_services(db)
    
    app = app_service.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=APP_NOT_FOUND_MSG
        )
    
    if not collaboration_service.can_user_manage_app(user_id, app_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only app owners can update apps"
        )
    
    update_dict = {
        'app_id': app_id,
        'name': app_data.name,
        'langsmith_api_key': app_data.langsmith_api_key,
        'agent_rate_limit': app_data.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT,
        'max_file_size_mb': app_data.max_file_size_mb or DEFAULT_MAX_FILE_SIZE_MB,
        'agent_cors_origins': app_data.agent_cors_origins
    }
    
    # Update app using service
    updated_app = app_service.create_or_update_app(update_dict)
    
    # Get owner information
    owner_email = None
    owner_name = None
    if updated_app.owner:
        owner_email = updated_app.owner.email
        owner_name = updated_app.owner.name
    
    return AppDetailSchema(
        app_id=updated_app.app_id,
        name=updated_app.name,
        langsmith_api_key=updated_app.langsmith_api_key or "",
        user_role="owner",
        created_at=updated_app.create_date,
        owner_id=updated_app.owner_id,
        owner_email=owner_email,
        owner_name=owner_name,
        agent_rate_limit=updated_app.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT,
        max_file_size_mb=updated_app.max_file_size_mb or DEFAULT_MAX_FILE_SIZE_MB,
        agent_cors_origins=updated_app.agent_cors_origins
    )


@apps_router.delete("/{app_id}",
                   summary="Delete app",
                   tags=["Apps"])
async def delete_app(
    app_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("owner")),
    db: Session = Depends(get_db)
):
    """
    Delete an app. Only owners can delete apps.
    """
    user_id = int(auth_context.identity.id)  # Extract DB user_id from enriched context
    
    app_service, collaboration_service = get_services(db)
    
    # Get app and verify ownership
    app = app_service.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=APP_NOT_FOUND_MSG
        )
    
    if not collaboration_service.can_user_manage_app(user_id, app_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only app owners can delete apps"
        )
    
    # Delete app using service
    success = app_service.delete_app(app_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete app"
        )
    
    return MessageResponseSchema(message="App deleted successfully")


@apps_router.post("/{app_id}/validate-langsmith-key",
                 summary="Validate LangSmith API key",
                 tags=["Apps"],
                 response_model=MessageResponseSchema)
async def validate_langsmith_key(
    app_id: int,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Validate the LangSmith API key configured for an app.
    Tests connectivity to the LangSmith API and returns the result.
    """
    import langsmith as ls

    app_service, _ = get_services(db)
    app = app_service.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=APP_NOT_FOUND_MSG
        )

    if not app.langsmith_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No LangSmith API key configured for this app"
        )

    try:
        client = ls.Client(
            api_key=app.langsmith_api_key,
            api_url="https://api.smith.langchain.com",
        )
        settings = client._get_settings()
        tenant_handle = getattr(settings, 'tenant_handle', None)
        logger.info(
            f"LangSmith API key validated for app '{app.name}'. "
            f"Tenant: {tenant_handle or 'default'}"
        )
        return MessageResponseSchema(
            message=f"LangSmith API key is valid. "
                    f"Tenant: {tenant_handle or 'default'}. "
                    f"Traces will be sent to project '{app.name}'."
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(
            f"LangSmith API key validation failed for app '{app.name}': "
            f"{type(e).__name__}: {error_msg}"
        )
        if "403" in error_msg or "Forbidden" in error_msg:
            detail = (
                "LangSmith API key is invalid or expired. "
                "Generate a new key at https://smith.langchain.com/settings"
            )
        elif "401" in error_msg or "Unauthorized" in error_msg:
            detail = "LangSmith API key is missing or malformed."
        else:
            detail = f"Cannot connect to LangSmith: {error_msg}"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )


@apps_router.post("/{app_id}/leave",
                 summary="Leave app collaboration",
                 tags=["Apps"],
                 response_model=MessageResponseSchema)
async def leave_app(
    app_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    Leave an app collaboration (for editors only).
    """
    user_id = int(auth_context.identity.id)  # Extract DB user_id from enriched context
    
    _, collaboration_service = get_services(db)
    
    # Check if user has access to the app
    user_role = collaboration_service.get_user_app_role(user_id, app_id)
    
    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App not found or access denied"
        )
    
    # Use the new leave_app_collaboration method
    try:
        success = collaboration_service.leave_app_collaboration(app_id, user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to leave app"
            )
        
        logger.info(f"User {user_id} left app {app_id}")
        return MessageResponseSchema(message="Successfully left the app")
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error leaving app {app_id} for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to leave app"
        )
