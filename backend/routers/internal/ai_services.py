from fastapi import APIRouter, Depends, HTTPException, status
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from typing import List

# Import database dependency
from db.database import get_db

# Import services
from services.ai_service_service import AIServiceService

# Import schemas and auth
from schemas.ai_service_schemas import AIServiceListItemSchema, AIServiceDetailSchema, CreateUpdateAIServiceSchema
from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)


ai_services_router = APIRouter()

AI_SERVICE_NOT_FOUND_ERROR = "AI service not found"

#AI SERVICE MANAGEMENT

@ai_services_router.get("/", 
                        summary="List AI services",
                        tags=["AI Services"],
                        response_model=List[AIServiceListItemSchema])
async def list_ai_services(
    app_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    List all AI services for a specific app.
    """    
    
    try:
        return AIServiceService.get_ai_services_by_app_id(db, app_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving AI services: {str(e)}"
        )


@ai_services_router.get("/{service_id}",
                        summary="Get AI service details",
                        tags=["AI Services"],
                        response_model=AIServiceDetailSchema)
async def get_ai_service(
    app_id: int, 
    service_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific AI service.
    """    
    
    try:
        result = AIServiceService.get_ai_service_detail(db, app_id, service_id)
        if result is None and service_id != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=AI_SERVICE_NOT_FOUND_ERROR
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving AI service: {str(e)}"
        )


@ai_services_router.post("/{service_id}",
                         summary="Create or update AI service",
                         tags=["AI Services"],
                         response_model=AIServiceDetailSchema)
async def create_or_update_ai_service(
    app_id: int,
    service_id: int,
    service_data: CreateUpdateAIServiceSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Create a new AI service or update an existing one.
    """
    
    try:
        result = AIServiceService.create_or_update_ai_service(db, app_id, service_id, service_data)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=AI_SERVICE_NOT_FOUND_ERROR
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating AI service: {str(e)}"
        )

@ai_services_router.post("/{service_id}/copy",
                         summary="Copy AI service",
                         tags=["AI Services"],
                         response_model=AIServiceDetailSchema)
async def copy_ai_service(
    app_id: int,
    service_id: int,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Copy an existing AI service.
    """
    try:
        result = AIServiceService.copy_ai_service(db, app_id, service_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=AI_SERVICE_NOT_FOUND_ERROR
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error copying AI service: {str(e)}"
        )
    

@ai_services_router.delete("/{service_id}",
                           summary="Delete AI service",
                           tags=["AI Services"])
async def delete_ai_service(
    app_id: int, 
    service_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Delete an AI service.
    """
    
    try:
        success = AIServiceService.delete_ai_service(db, app_id, service_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=AI_SERVICE_NOT_FOUND_ERROR
            )
        
        return {"message": "AI service deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting AI service: {str(e)}"
        ) 