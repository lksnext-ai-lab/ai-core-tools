from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import Optional
from sqlalchemy.orm import Session

from db.database import get_db
from routers.internal.auth_utils import get_current_user_oauth
from schemas.ocr_schemas import OCRResponseSchema
from services.agent_execution_service import AgentExecutionService
from utils.logger import get_logger

logger = get_logger(__name__)

ocr_router = APIRouter(tags=["Internal OCR"])


@ocr_router.post("/{agent_id}/process",
                 summary="Process OCR",
                 tags=["Internal OCR"],
                 response_model=OCRResponseSchema)
async def process_ocr_internal(
    agent_id: int,
    pdf_file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Internal API: Process OCR for playground (OAuth authentication)
    """
    try:
        # Create user context for OAuth user
        user_context = {
            "user_id": current_user["user_id"],
            "oauth": True,
            "app_id": current_user.get("app_id")
        }
        
        # Use unified service layer
        execution_service = AgentExecutionService(db)
        result = await execution_service.execute_agent_ocr(
            agent_id=agent_id,
            pdf_file=pdf_file,
            user_context=user_context,
            db=db
        )
        
        logger.info(f"OCR processing completed for agent {agent_id} by user {current_user['user_id']}")
        return OCRResponseSchema(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in OCR processing endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="OCR processing failed") 