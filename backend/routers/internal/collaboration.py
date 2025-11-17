from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Tuple
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

# Import database
from db.database import get_db

# Import services
from services.app_collaboration_service import AppCollaborationService
from services.app_service import AppService

# Import schemas and auth
from schemas.apps_schemas import (
    CollaboratorListItemSchema, CollaboratorDetailSchema, 
    InviteCollaboratorSchema, UpdateCollaboratorRoleSchema,
    InvitationResponseSchema
)
from schemas.common_schemas import MessageResponseSchema
from .auth_utils import get_current_user_oauth

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

collaboration_router = APIRouter()


# Helper function to get services and avoid code duplication
def get_services(db: Session) -> Tuple[AppService, AppCollaborationService]:
    """Get app and collaboration services instances."""
    return AppService(db), AppCollaborationService(db)


# ==================== COLLABORATION MANAGEMENT ====================

@collaboration_router.get("/", 
                           summary="List app collaborators",
                           tags=["Collaboration"],
                           response_model=List[CollaboratorListItemSchema])
async def list_collaborators(
    app_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    List all collaborators for a specific app.
    """
    user_id = auth_context.identity.id
    
    try:
        _, collaboration_service = get_services(db)
        
        # Check if user can access this app
        if not collaboration_service.can_user_access_app(user_id, app_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this app"
            )
        
        collaborators = collaboration_service.get_app_collaborators(app_id)
        
        result = []
        for collab in collaborators:
            result.append(CollaboratorListItemSchema(
                id=collab.id,
                user_id=collab.user_id,
                user_email=collab.user.email if collab.user else "Unknown",
                user_name=collab.user.name if collab.user else "Unknown",
                role=collab.role.value,
                status=collab.status.value,
                invited_at=collab.invited_at,
                accepted_at=collab.accepted_at,
                invited_by_name=collab.inviter.name if collab.inviter else "Unknown"
            ))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving collaborators: {str(e)}"
        )


@collaboration_router.post("/invite",
                          summary="Invite collaborator",
                          tags=["Collaboration"],
                          response_model=CollaboratorDetailSchema)
async def invite_collaborator(
    app_id: int,
    invitation_data: InviteCollaboratorSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Invite a user to collaborate on an app.
    """
    user_id = auth_context.identity.id
    
    try:
        _, collaboration_service = get_services(db)
        
        # Check if user can manage collaborators (owner only)
        if not collaboration_service.can_user_manage_app(user_id, app_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only app owners can invite collaborators"
            )
        
        collaboration = collaboration_service.invite_user_to_app(
            app_id=app_id,
            user_email=invitation_data.email,
            invited_by_user_id=user_id,
            role=invitation_data.role
        )
        
        if not collaboration:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send invitation"
            )
        
        from models.user import User
        user_data = db.query(User).filter(User.user_id == collaboration.user_id).first()
        inviter_data = db.query(User).filter(User.user_id == collaboration.invited_by).first()
        
        return CollaboratorDetailSchema(
            id=collaboration.id,
            app_id=app_id,
            user_id=collaboration.user_id,
            role=collaboration.role.value,
            status=collaboration.status.value,
            invited_by=collaboration.invited_by,
            invited_at=collaboration.invited_at,
            accepted_at=collaboration.accepted_at,
            user={
                "user_id": user_data.user_id,
                "email": user_data.email,
                "name": user_data.name
            } if user_data else None,
            inviter={
                "user_id": inviter_data.user_id,
                "email": inviter_data.email,
                "name": inviter_data.name
            } if inviter_data else None
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error sending invitation: {str(e)}"
        )


@collaboration_router.put("/{user_id}/role",
                         summary="Update collaborator role",
                         tags=["Collaboration"],
                         response_model=MessageResponseSchema)
async def update_collaborator_role(
    app_id: int,
    user_id: int,
    role_data: UpdateCollaboratorRoleSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Update a collaborator's role.
    """
    current_user_id = auth_context.identity.id
    
    try:
        _, collaboration_service = get_services(db)
        
        success = collaboration_service.update_collaborator_role(
            app_id=app_id,
            user_id=user_id,
            new_role=role_data.role,
            updated_by_user_id=current_user_id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update role"
            )
        
        return MessageResponseSchema(message="Role updated successfully")
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating role: {str(e)}"
        )


@collaboration_router.delete("/{user_id}",
                            summary="Remove collaborator",
                            tags=["Collaboration"],
                            response_model=MessageResponseSchema)
async def remove_collaborator(
    app_id: int,
    user_id: int,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Remove a collaborator from an app.
    """
    current_user_id = auth_context.identity.id
    
    try:
        _, collaboration_service = get_services(db)
        
        success = collaboration_service.remove_collaborator(
            app_id=app_id,
            user_id=user_id,
            removed_by_user_id=current_user_id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to remove collaborator"
            )
        
        return MessageResponseSchema(message="Collaborator removed successfully")
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error removing collaborator: {str(e)}"
        )


# ==================== INVITATION RESPONSES ====================

@collaboration_router.post("/invitations/{collaboration_id}/respond",
                           summary="Respond to invitation",
                           tags=["Collaboration"],
                           response_model=MessageResponseSchema)
async def respond_to_invitation(
    collaboration_id: int,
    response_data: InvitationResponseSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Accept or decline a collaboration invitation.
    """
    user_id = auth_context.identity.id
    
    try:
        _, collaboration_service = get_services(db)
        
        success = collaboration_service.respond_to_invitation(
            invitation_id=collaboration_id,
            user_id=user_id,
            action=response_data.action
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid invitation or action"
            )
        
        action_message = "accepted" if response_data.action == "accept" else "declined"
        return MessageResponseSchema(message=f"Invitation {action_message} successfully")
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error responding to invitation: {str(e)}"
        )


@collaboration_router.get("/my-invitations",
                         summary="Get my pending invitations",
                         tags=["Collaboration"],
                         response_model=List[CollaboratorListItemSchema])
async def get_my_invitations(
    auth_context: AuthContext = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Get all pending collaboration invitations for the current user.
    """
    user_id = auth_context.identity.id
    
    try:
        _, collaboration_service = get_services(db)
        
        invitations = collaboration_service.get_user_pending_invitations(user_id)
        
        result = []
        for invitation in invitations:
            result.append(CollaboratorListItemSchema(
                id=invitation.id,
                user_id=invitation.user_id,
                user_email=invitation.user.email if invitation.user else "Unknown",
                user_name=invitation.user.name if invitation.user else "Unknown",
                role=invitation.role.value,
                status=invitation.status.value,
                invited_at=invitation.invited_at,
                accepted_at=invitation.accepted_at,
                invited_by_name=invitation.inviter.name if invitation.inviter else "Unknown"
            ))
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving invitations: {str(e)}"
        ) 