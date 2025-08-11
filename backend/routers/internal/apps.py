from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Tuple
from sqlalchemy.orm import Session

# Import database
from db.database import get_db

# Import services
from services.app_service import AppService
from services.app_collaboration_service import AppCollaborationService

# Import schemas and auth
from schemas.apps_schemas import (
    AppListItemSchema, AppDetailSchema, CreateAppSchema, UpdateAppSchema
)
from schemas.common_schemas import MessageResponseSchema
from .auth_utils import get_current_user_oauth

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

apps_router = APIRouter()

# ==================== HELPER FUNCTIONS ====================

def get_services(db: Session) -> Tuple[AppService, AppCollaborationService]:
    """
    Helper function to initialize and return app services.
    """
    app_service = AppService(db)
    collaboration_service = AppCollaborationService(db)
    return app_service, collaboration_service

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
    try:
        # Import services needed for counting
        from services.agent_service import AgentService
        from services.repository_service import RepositoryService
        from services.domain_service import DomainService
        from services.silo_service import SiloService
        
        # Count agents
        agent_service = AgentService()
        agents = agent_service.get_agents(app_id)
        agent_count = len(agents) if agents else 0
        
        # Count repositories
        repositories = RepositoryService.get_repositories_by_app_id(app_id, db)
        repository_count = len(repositories) if repositories else 0
        
        # Count domains
        domains = DomainService.get_domains_by_app_id(app_id, db)
        domain_count = len(domains) if domains else 0
        
        # Count silos
        silos = SiloService.get_silos_by_app_id(app_id, db)
        silo_count = len(silos) if silos else 0
        
        # Count collaborators
        collaborators = collaboration_service.get_app_collaborators(app_id)
        collaborator_count = len(collaborators) if collaborators else 0
        
        return {
            'agent_count': agent_count,
            'repository_count': repository_count,
            'domain_count': domain_count,
            'silo_count': silo_count,
            'collaborator_count': collaborator_count
        }
        
    except Exception as e:
        logger.warning(f"Error calculating counts for app {app_id}: {str(e)}")
        # Fallback to 0 if there are any errors
        return {
            'agent_count': 0,
            'repository_count': 0,
            'domain_count': 0,
            'silo_count': 0,
            'collaborator_count': 0
        }

# ==================== APP MANAGEMENT ====================

@apps_router.get("/", 
                summary="List user's apps",
                tags=["Apps"],
                response_model=List[AppListItemSchema])
async def list_apps(
    current_user: dict = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    List all apps that the current user owns or collaborates on.
    """
    user_id = current_user["user_id"]
    
    app_service, collaboration_service = get_services(db)
    
    apps = app_service.get_apps(user_id)
    
    # Convert to schema
    app_list = []
    for app in apps:
        role = collaboration_service.get_user_app_role(user_id, app.app_id) or "owner"
        
        # Calculate entity counts using helper function
        counts = calculate_app_entity_counts(app.app_id, db, collaboration_service)
        
        app_item = AppListItemSchema(
            app_id=app.app_id,
            name=app.name,
            role=role,
            created_at=app.create_date,
            langsmith_configured=bool(app.langsmith_api_key),
            owner_id=app.owner_id,
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
    current_user: dict = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific app.
    """
    user_id = current_user["user_id"]
    
    app_service, collaboration_service = get_services(db)
    
    # Get app and verify access
    app = app_service.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App not found"
        )
    
    # Check if user has access to this app
    if not collaboration_service.can_user_access_app(user_id, app_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this app"
        )
    
    user_role = collaboration_service.get_user_app_role(user_id, app_id)
    
    # Calculate entity counts using helper function
    counts = calculate_app_entity_counts(app_id, db, collaboration_service)
    
    return AppDetailSchema(
        app_id=app.app_id,
        name=app.name,
        langsmith_api_key=app.langsmith_api_key or "",
        user_role=user_role,
        created_at=app.create_date,
        owner_id=app.owner_id,
        **counts  # Unpack the counts dictionary
    )


@apps_router.post("/",
                 summary="Create new app",
                 tags=["Apps"],
                 response_model=AppDetailSchema,
                 status_code=status.HTTP_201_CREATED)
async def create_app(
    app_data: CreateAppSchema,
    current_user: dict = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Create a new app for the current user.
    """
    user_id = current_user["user_id"]
    
    app_service, _ = get_services(db)
    
    # Prepare app data
    app_dict = {
        'name': app_data.name,
        'owner_id': user_id,
        'langsmith_api_key': app_data.langsmith_api_key
    }
    
    # Create app using service
    app = app_service.create_or_update_app(app_dict)
    
    return AppDetailSchema(
        app_id=app.app_id,
        name=app.name,
        langsmith_api_key=app.langsmith_api_key or "",
        user_role="owner",
        created_at=app.create_date,
        owner_id=app.owner_id
    )


@apps_router.put("/{app_id}",
                summary="Update app",
                tags=["Apps"],
                response_model=AppDetailSchema)
async def update_app(
    app_id: int,
    app_data: UpdateAppSchema,
    current_user: dict = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Update an existing app. Only owners can update apps.
    """
    user_id = current_user["user_id"]
    
    app_service, collaboration_service = get_services(db)
    
    # Get app and verify ownership
    app = app_service.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App not found"
        )
    
    # Check if user is owner
    if not collaboration_service.can_user_manage_app(user_id, app_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only app owners can update apps"
        )
    
    # Prepare update data
    update_dict = {
        'app_id': app_id,
        'name': app_data.name,
        'langsmith_api_key': app_data.langsmith_api_key
    }
    
    # Update app using service
    updated_app = app_service.create_or_update_app(update_dict)
    
    return AppDetailSchema(
        app_id=updated_app.app_id,
        name=updated_app.name,
        langsmith_api_key=updated_app.langsmith_api_key or "",
        user_role="owner",
        created_at=updated_app.create_date,
        owner_id=updated_app.owner_id
    )


@apps_router.delete("/{app_id}",
                   summary="Delete app",
                   tags=["Apps"])
async def delete_app(
    app_id: int, 
    current_user: dict = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Delete an app. Only owners can delete apps.
    """
    user_id = current_user["user_id"]
    
    app_service, collaboration_service = get_services(db)
    
    # Get app and verify ownership
    app = app_service.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App not found"
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


@apps_router.post("/{app_id}/leave",
                 summary="Leave app collaboration",
                 tags=["Apps"],
                 response_model=MessageResponseSchema)
async def leave_app(
    app_id: int, 
    current_user: dict = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Leave an app collaboration (for editors only).
    """
    user_id = current_user["user_id"]
    
    _, collaboration_service = get_services(db)
    
    # Check if user is a collaborator (not owner)
    user_role = collaboration_service.get_user_app_role(user_id, app_id)
    
    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App not found or access denied"
        )
    
    if user_role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="App owners cannot leave their own apps"
        )
    
    # Remove collaboration
    try:
        success = collaboration_service.remove_collaborator(app_id, user_id, user_id)
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
