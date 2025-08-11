from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
import json
import tempfile
import os

# Import our services
from services.agent_service import AgentService
from services.silo_service import SiloService
from services.repository_service import RepositoryService
from services.resource_service import ResourceService

# Import Pydantic models and auth
from .schemas import *
from .auth import get_api_key_auth, validate_api_key_for_app, APIKeyAuth
from db.database import get_db

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

ocr_router = APIRouter()

# ==================== OCR ENDPOINTS ====================

@ocr_router.post("/{agent_id}/process",
                 summary="Process OCR",
                 tags=["OCR"],
                 response_model=OCRResponseSchema)
async def process_ocr(
    app_id: int,
    agent_id: int,
    pdf: UploadFile = File(...),
    api_key: str = Depends(get_api_key_auth),
    db: Session = Depends(get_db)
):
    """Process OCR on a PDF file using the specified agent."""
    # Validate API key for this app
    auth = validate_api_key_for_app(app_id, api_key)
    
    # Validate file type
    if not pdf.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Create user context for API key user
    user_context = {
        "api_key": api_key,
        "app_id": app_id,
        "oauth": False
    }
    
    # Use unified service layer
    from services.agent_execution_service import AgentExecutionService
    execution_service = AgentExecutionService(db)
    
    try:
        result = await execution_service.execute_agent_ocr(
            agent_id=agent_id,
            pdf_file=pdf,
            user_context=user_context,
            for_api=True,  # This ensures we return structured content only
            db=db
        )
        
        # For API, we return the structured content
        if isinstance(result, dict):
            # Extract relevant info for API response
            content = result.get("content", "")
            pages_count = len(result.get("pages", []))
            confidence = result.get("confidence", 0.0)
            
            # If content is a dict (structured output), convert to string for API
            if isinstance(content, dict):
                import json
                text_content = json.dumps(content, indent=2, ensure_ascii=False)
            else:
                text_content = str(content)
            
            return OCRResponseSchema(
                text=text_content,
                pages=pages_count if pages_count > 0 else 1,
                confidence=confidence
            )
        else:
            # Fallback for simple string result
            return OCRResponseSchema(
                text=str(result),
                pages=1,
                confidence=0.8
            )
        
    except Exception as e:
        logger.error(f"Error in public OCR endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="OCR processing failed") 