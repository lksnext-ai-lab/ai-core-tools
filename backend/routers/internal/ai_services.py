from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional

# Import models for enum access
from models.ai_service import ProviderEnum

# Import schemas and auth
from .schemas import *
# Switch to Google OAuth auth instead of temp token auth
from routers.auth import verify_jwt_token

ai_services_router = APIRouter()

# ==================== AUTHENTICATION ====================

async def get_current_user_oauth(request: Request):
    """
    Get current authenticated user using Google OAuth JWT tokens.
    Compatible with the frontend auth system.
    """
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please provide Authorization header with Bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = auth_header.split(' ')[1]
        
        # Verify token using Google OAuth system
        payload = verify_jwt_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return payload
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

# ==================== AI SERVICE MANAGEMENT ====================

@ai_services_router.get("/", 
                        summary="List AI services",
                        tags=["AI Services"],
                        response_model=List[AIServiceListItemSchema])
async def list_ai_services(app_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    List all AI services for a specific app.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.ai_service import AIService
        
        session = SessionLocal()
        try:
            ai_services = session.query(AIService).filter(AIService.app_id == app_id).all()
            
            result = []
            for service in ai_services:
                result.append(AIServiceListItemSchema(
                    service_id=service.service_id,
                    name=service.name,
                    provider=service.provider.value if hasattr(service.provider, 'value') else service.provider,
                    model_name=service.description or "",  # Use description as model info
                    created_at=service.create_date
                ))
            
            return result
            
        finally:
            session.close()
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving AI services: {str(e)}"
        )


@ai_services_router.get("/{service_id}",
                        summary="Get AI service details",
                        tags=["AI Services"],
                        response_model=AIServiceDetailSchema)
async def get_ai_service(app_id: int, service_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Get detailed information about a specific AI service.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.ai_service import AIService
        
        session = SessionLocal()
        try:
            if service_id == 0:
                # New AI service
                # Get available providers for the form
                providers = [{"value": p.value, "name": p.value} for p in ProviderEnum]
                
                return AIServiceDetailSchema(
                    service_id=0,
                    name="",
                    provider=None,
                    model_name="",
                    api_key="",
                    base_url="",
                    created_at=None,
                    # Form data
                    available_providers=providers
                )
            
            # Existing AI service
            service = session.query(AIService).filter(
                AIService.service_id == service_id,
                AIService.app_id == app_id
            ).first()
            
            if not service:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="AI service not found"
                )
            
            # Get available providers for the form
            providers = [{"value": p.value, "name": p.value} for p in ProviderEnum]
            
            return AIServiceDetailSchema(
                service_id=service.service_id,
                name=service.name,
                provider=service.provider.value if hasattr(service.provider, 'value') else service.provider,
                model_name=service.description or "",
                api_key=service.api_key,
                base_url=service.endpoint or "",  # Use endpoint as base_url
                created_at=service.create_date,
                available_providers=providers
            )
            
        finally:
            session.close()
            
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
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Create a new AI service or update an existing one.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.ai_service import AIService, ProviderEnum
        from datetime import datetime
        
        session = SessionLocal()
        try:
            if service_id == 0:
                # Create new AI service
                service = AIService()
                service.app_id = app_id
                service.create_date = datetime.now()
            else:
                # Update existing AI service
                service = session.query(AIService).filter(
                    AIService.service_id == service_id,
                    AIService.app_id == app_id
                ).first()
                
                if not service:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="AI service not found"
                    )
            
            # Update service data
            service.name = service_data.name
            service.provider = service_data.provider  # Store as string, not enum
            service.description = service_data.model_name  # Store model name in description
            service.api_key = service_data.api_key
            service.endpoint = service_data.base_url  # Store base_url in endpoint
            
            session.add(service)
            session.commit()
            session.refresh(service)
            
            # Return updated service (reuse the GET logic)
            return await get_ai_service(app_id, service.service_id, current_user)
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating AI service: {str(e)}"
        )


@ai_services_router.delete("/{service_id}",
                           summary="Delete AI service",
                           tags=["AI Services"])
async def delete_ai_service(app_id: int, service_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Delete an AI service.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.ai_service import AIService
        
        session = SessionLocal()
        try:
            service = session.query(AIService).filter(
                AIService.service_id == service_id,
                AIService.app_id == app_id
            ).first()
            
            if not service:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="AI service not found"
                )
            
            session.delete(service)
            session.commit()
            
            return {"message": "AI service deleted successfully"}
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting AI service: {str(e)}"
        ) 