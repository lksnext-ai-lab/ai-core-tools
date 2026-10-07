from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import Annotated
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

from db.database import get_db
from routers.internal.auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole
from schemas.ocr_schemas import OCRResponseSchema
from services.agent_service import AgentService
from services.agent_execution_service import AgentExecutionService
from utils.logger import get_logger

logger = get_logger(__name__)

ocr_router = APIRouter(tags=["Internal OCR"])

_OCR_AGENT_NOT_FOUND = "OCR agent not found"


def _get_ocr_agent_or_404(db: Session, agent_id: int, app_id: int):
    """Get the OCR agent by ID, 404 if missing or if it belongs to a different app.

    Mirrors ``_get_agent_or_404`` in routers/internal/agents.py: the error message
    never reveals whether the agent exists under a different app.
    """
    agent = AgentService().get_agent(db, agent_id, agent_type='ocr_agent')
    if not agent or agent.app_id != app_id:
        raise HTTPException(status_code=404, detail=_OCR_AGENT_NOT_FOUND)
    return agent


@ocr_router.post(
    "/{agent_id}/process",
    summary="Process OCR",
    tags=["Internal OCR"],
    response_model=OCRResponseSchema,
    responses={
        404: {"description": "OCR agent not found"},
        500: {
            "description": "OCR processing failed",
            "content": {
                "application/json": {
                    "example": {"detail": "OCR processing failed"}
                }
            },
        }
    },
)
async def process_ocr_internal(
    app_id: int,
    agent_id: int,
    pdf_file: Annotated[UploadFile, File(...)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    db: Annotated[Session, Depends(get_db)]
):
    """
    Internal API: Process OCR for playground (OAuth authentication)
    """
    try:
        # Verify the OCR agent exists and belongs to this app before running it —
        # otherwise a member of one app could invoke another app's OCR agent
        # (and its vision/text AI service credentials) via this app's path.
        _get_ocr_agent_or_404(db, agent_id, app_id)

        # Create user context for OAuth user
        user_context = {
            "user_id": int(auth_context.identity.id),
            "oauth": True,
            "app_id": app_id,
        }

        # Use unified service layer
        execution_service = AgentExecutionService()
        result = await execution_service.execute_agent_ocr(
            agent_id=agent_id,
            pdf_file=pdf_file,
            user_context=user_context,
            db=db
        )

        logger.info(f"OCR processing completed for agent {agent_id} by user {int(auth_context.identity.id)}")
        return OCRResponseSchema(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in OCR processing endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="OCR processing failed") 