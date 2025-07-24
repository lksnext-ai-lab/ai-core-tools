from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

# Import services
from services.app_service import AppService
from services.app_collaboration_service import AppCollaborationService

# Import schemas and auth
from .schemas import *
from .auth_utils import get_current_user_oauth

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

apps_router = APIRouter()

# ==================== APP MANAGEMENT ====================

@apps_router.get("/", 
                summary="List user's apps",
                tags=["Apps"],
                response_model=List[AppListItemSchema])
async def list_apps(current_user: dict = Depends(get_current_user_oauth)):
    """
    List all apps that the current user owns or collaborates on.
    """
    user_id = current_user["user_id"]
    
    # Use the collaboration service method that already handles duplicates properly
    accessible_apps = AppCollaborationService.get_user_accessible_apps(user_id)
    
    # Format response
    apps = []
    
    # Import User model to get owner info
    from models.user import User
    from db.session import SessionLocal
    
    session = SessionLocal()
    try:
        for app in accessible_apps:
            # Get owner info
            owner = session.query(User).filter(User.user_id == app.owner_id).first()
            
            # Determine user's role in this app
            if app.owner_id == user_id:
                role = "owner"
            else:
                # Get user's role as collaborator
                role = AppCollaborationService.get_user_app_role(user_id, app.app_id) or "editor"
            
            apps.append(AppListItemSchema(
                app_id=app.app_id,
                name=app.name,
                role=role,
                created_at=app.create_date,
                langsmith_configured=bool(app.langsmith_api_key),
                owner_id=app.owner_id,
                owner_name=owner.name if owner else None,
                owner_email=owner.email if owner else None
            ))
    
    finally:
        session.close()
    
    return apps


@apps_router.get("/{app_id}",
                summary="Get app details",
                tags=["Apps"], 
                response_model=AppDetailSchema)
async def get_app(app_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Get detailed information about a specific app.
    """
    user_id = current_user["user_id"]
    
    # Get app and verify access
    app = AppService.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App not found"
        )
    
    # Check if user has access to this app
    user_role = app.get_user_role(user_id)
    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this app"
        )
    
    return AppDetailSchema(
        app_id=app.app_id,
        name=app.name,
        langsmith_api_key=app.langsmith_api_key or "",
        user_role=user_role,
        created_at=app.create_date,
        owner_id=app.owner_id
    )


@apps_router.post("/",
                 summary="Create new app",
                 tags=["Apps"],
                 response_model=AppDetailSchema,
                 status_code=status.HTTP_201_CREATED)
async def create_app(
    app_data: CreateAppSchema,
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Create a new app for the current user.
    """
    user_id = current_user["user_id"]
    
    # Prepare app data
    app_dict = {
        'name': app_data.name,
        'owner_id': user_id,
        'langsmith_api_key': app_data.langsmith_api_key
    }
    
    # Create app using service
    app = AppService.create_or_update_app(app_dict)
    
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
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Update an existing app. Only owners can update apps.
    """
    user_id = current_user["user_id"]
    
    # Get app and verify ownership
    app = AppService.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App not found"
        )
    
    # Check if user is owner or has access (simplified for development)
    user_role = app.get_user_role(user_id) if hasattr(app, 'get_user_role') else None
    
    # For development: allow access if user is owner OR if get_user_role doesn't work
    if user_role != "owner" and app.owner_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only app owners can update apps"
        )
    
    # Set user_role for response
    user_role = "owner" if app.owner_id == user_id else (user_role or "collaborator")
    
    # Prepare update data
    update_dict = {
        'app_id': app_id,
        'name': app_data.name,
        'langsmith_api_key': app_data.langsmith_api_key
    }
    
    # Update app using service
    updated_app = AppService.create_or_update_app(update_dict)
    
    return AppDetailSchema(
        app_id=updated_app.app_id,
        name=updated_app.name,
        langsmith_api_key=updated_app.langsmith_api_key or "",
        user_role=user_role,
        created_at=updated_app.create_date,
        owner_id=updated_app.owner_id
    )


@apps_router.delete("/{app_id}",
                   summary="Delete app",
                   tags=["Apps"])
async def delete_app(app_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Delete an app. Only owners can delete apps.
    """
    user_id = current_user["user_id"]
    
    # Get app and verify ownership
    app = AppService.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App not found"
        )
    
    user_role = app.get_user_role(user_id)
    if user_role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only app owners can delete apps"
        )
    
    # Delete app using service
    success = AppService.delete_app(app_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete app"
        )
    
    return {"message": "App deleted successfully"}

@apps_router.post("/{app_id}/leave",
                 summary="Leave app collaboration",
                 tags=["Apps"])
async def leave_app(app_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Leave an app collaboration (for editors only).
    """
    user_id = current_user["user_id"]
    
    # Check if user is a collaborator (not owner)
    user_role = AppCollaborationService.get_user_app_role(user_id, app_id)
    
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
        # For self-leave, we need a special method or modify the existing one
        # Since the user is leaving themselves, we'll handle it directly
        from db.session import SessionLocal
        from models.app_collaborator import AppCollaborator
        
        session = SessionLocal()
        try:
            # Find and delete the collaboration
            collaboration = session.query(AppCollaborator).filter(
                AppCollaborator.app_id == app_id,
                AppCollaborator.user_id == user_id
            ).first()
            
            if not collaboration:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Collaboration not found"
                )
            
            session.delete(collaboration)
            session.commit()
            
            logger.info(f"User {user_id} left app {app_id}")
            return {"message": "Successfully left the app"}
            
        finally:
            session.close()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error leaving app {app_id} for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to leave app"
        ) 