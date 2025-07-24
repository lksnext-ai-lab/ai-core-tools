from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional

# Import schemas and auth
from .schemas import *
from .auth_utils import get_current_user_oauth

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

collaboration_router = APIRouter()

# ==================== COLLABORATION MANAGEMENT ====================

@collaboration_router.get("/", 
                           summary="List app collaborators",
                           tags=["Collaboration"],
                           response_model=List[CollaboratorListItemSchema])
async def list_collaborators(app_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    List all collaborators for a specific app.
    """
    user_id = current_user["user_id"]
    
    try:
        from services.app_collaboration_service import AppCollaborationService
        
        # Check if user can access this app
        if not AppCollaborationService.can_user_access_app(user_id, app_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this app"
            )
        
        collaborators = AppCollaborationService.get_app_collaborators(app_id)
        
        result = []
        for collab in collaborators:
            result.append(CollaboratorListItemSchema(
                id=collab.id,
                user_id=collab.user_id,
                user_email=collab.user.email if collab.user else "Unknown",
                user_name=collab.user.name if collab.user else None,
                role=collab.role.value,
                status=collab.status.value,
                invited_by=collab.invited_by,
                inviter_email=collab.inviter.email if collab.inviter else "Unknown",
                invited_at=collab.invited_at,
                accepted_at=collab.accepted_at
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
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Invite a user to collaborate on an app.
    """
    user_id = current_user["user_id"]
    
    try:
        from services.app_collaboration_service import AppCollaborationService
        
        # Check if user can manage this app (owner only)
        if not AppCollaborationService.can_user_manage_app(user_id, app_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only app owners can invite collaborators"
            )
        
        collaboration = AppCollaborationService.invite_user_to_app(
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
        
        # Load user and inviter data for response
        from db.session import SessionLocal
        from models.user import User
        session = SessionLocal()
        try:
            user_data = session.query(User).filter(User.user_id == collaboration.user_id).first()
            inviter_data = session.query(User).filter(User.user_id == collaboration.invited_by).first()
            
            return CollaboratorDetailSchema(
                id=collaboration.id,
                app_id=app_id,
                user_id=collaboration.user_id,
                user_email=user_data.email if user_data else "Unknown",
                user_name=user_data.name if user_data else None,
                role=collaboration.role.value,
                status=collaboration.status.value,
                invited_by=collaboration.invited_by,
                inviter_email=inviter_data.email if inviter_data else "Unknown",
                invited_at=collaboration.invited_at,
                accepted_at=collaboration.accepted_at
            )
        finally:
            session.close()
        
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
                         tags=["Collaboration"])
async def update_collaborator_role(
    app_id: int,
    user_id: int,
    role_data: UpdateCollaboratorRoleSchema,
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Update a collaborator's role.
    """
    current_user_id = current_user["user_id"]
    
    try:
        from services.app_collaboration_service import AppCollaborationService
        
        AppCollaborationService.update_collaborator_role(
            app_id=app_id,
            user_id=user_id,
            new_role=role_data.role,
            updated_by_user_id=current_user_id
        )
        
        return {"message": "Role updated successfully"}
        
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
                            tags=["Collaboration"])
async def remove_collaborator(
    app_id: int,
    user_id: int,
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Remove a collaborator from an app.
    """
    current_user_id = current_user["user_id"]
    
    try:
        from services.app_collaboration_service import AppCollaborationService
        
        AppCollaborationService.remove_collaborator(
            app_id=app_id,
            user_id=user_id,
            removed_by_user_id=current_user_id
        )
        
        return {"message": "Collaborator removed successfully"}
        
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
                           tags=["Collaboration"])
async def respond_to_invitation(
    collaboration_id: int,
    response_data: CollaborationResponseSchema,
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Accept or decline a collaboration invitation.
    """
    user_id = current_user["user_id"]
    
    try:
        from services.app_collaboration_service import AppCollaborationService
        
        AppCollaborationService.respond_to_invitation(
            collaboration_id=collaboration_id,
            user_id=user_id,
            action=response_data.action
        )
        
        action_message = "accepted" if response_data.action == "accept" else "declined"
        return {"message": f"Invitation {action_message} successfully"}
        
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
async def get_my_invitations(current_user: dict = Depends(get_current_user_oauth)):
    """
    Get all pending collaboration invitations for the current user.
    """
    user_id = current_user["user_id"]
    
    try:
        from services.app_collaboration_service import AppCollaborationService
        
        invitations = AppCollaborationService.get_user_pending_invitations(user_id)
        
        result = []
        for invitation in invitations:
            result.append(CollaboratorListItemSchema(
                id=invitation.id,
                user_id=invitation.user_id,
                user_email=current_user.get("email", "Unknown"),
                user_name=current_user.get("name"),
                role=invitation.role.value,
                status=invitation.status.value,
                invited_by=invitation.invited_by,
                inviter_email=invitation.inviter.email if invitation.inviter else "Unknown",
                invited_at=invitation.invited_at,
                accepted_at=invitation.accepted_at
            ))
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving invitations: {str(e)}"
        ) 