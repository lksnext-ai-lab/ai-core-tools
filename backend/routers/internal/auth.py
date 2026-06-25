"""Pending-invitation list and respond endpoints for the internal API."""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional, Annotated
from datetime import datetime
from db.database import get_db
from services.app_collaboration_service import AppCollaborationService
from utils.auth_config import AuthConfig
from utils.logger import get_logger
from lks_idprovider import AuthContext
from .auth_utils import get_current_user_oauth
from schemas.apps_schemas import InvitationResponseSchema

logger = get_logger(__name__)

AuthConfig.load_config()

router = APIRouter(tags=["auth"])


class PendingInvitationSchema(BaseModel):
    id: int
    app_id: int
    app_name: str
    inviter_email: str
    inviter_name: Optional[str] = None
    invited_at: datetime
    role: str


@router.get(
    "/pending-invitations",
    response_model=List[PendingInvitationSchema],
    summary="Get pending invitations",
    description="Get all pending collaboration invitations for the current user",
)
async def get_pending_invitations(
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    user_id = auth_context.identity.id
    collaboration_service = AppCollaborationService(db)
    
    invitations = collaboration_service.get_user_pending_invitations(user_id)
    
    result = []
    for inv in invitations:
        result.append(PendingInvitationSchema(
            id=inv.id,
            app_id=inv.app_id,
            app_name=inv.app.name if inv.app else "Unknown App",
            inviter_email=inv.inviter.email if inv.inviter else "Unknown",
            inviter_name=inv.inviter.name if inv.inviter else "Unknown",
            invited_at=inv.invited_at,
            role=inv.role.value
        ))
    
    return result


@router.post(
    "/invitations/{invitation_id}/respond",
    summary="Respond to invitation",
    description="Accept or decline a collaboration invitation",
)
async def respond_to_invitation(
    invitation_id: int,
    response: InvitationResponseSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    user_id = auth_context.identity.id
    collaboration_service = AppCollaborationService(db)
    
    success = collaboration_service.respond_to_invitation(
        invitation_id, user_id, response.action
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to respond to invitation. It may not exist, belong to you, or be pending."
        )
    
    return {"success": True, "message": f"Invitation {response.action}ed successfully"}
