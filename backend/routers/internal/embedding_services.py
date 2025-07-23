from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional

# Import models for enum access
from models.embedding_service import EmbeddingProvider

# Import schemas and auth
from .schemas import *
# Switch to Google OAuth auth instead of temp token auth
from routers.auth import verify_jwt_token

embedding_services_router = APIRouter()

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

# ==================== EMBEDDING SERVICE MANAGEMENT ====================

@embedding_services_router.get("/", 
                               summary="List embedding services",
                               tags=["Embedding Services"],
                               response_model=List[EmbeddingServiceListItemSchema])
async def list_embedding_services(app_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    List all embedding services for a specific app.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.embedding_service import EmbeddingService
        
        session = SessionLocal()
        try:
            embedding_services = session.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).all()
            
            result = []
            for service in embedding_services:
                result.append(EmbeddingServiceListItemSchema(
                    service_id=service.service_id,
                    name=service.name,
                    provider=service.provider.value if hasattr(service.provider, 'value') else service.provider,
                    model_name=service.description or "",
                    created_at=service.create_date
                ))
            
            return result
            
        finally:
            session.close()
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving embedding services: {str(e)}"
        )


@embedding_services_router.get("/{service_id}",
                               summary="Get embedding service details",
                               tags=["Embedding Services"],
                               response_model=EmbeddingServiceDetailSchema)
async def get_embedding_service(app_id: int, service_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Get detailed information about a specific embedding service.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.embedding_service import EmbeddingService
        
        session = SessionLocal()
        try:
            if service_id == 0:
                # New embedding service
                # Get available providers for the form
                providers = [{"value": p.value, "name": p.value} for p in EmbeddingProvider]
                
                return EmbeddingServiceDetailSchema(
                    service_id=0,
                    name="",
                    provider=None,
                    model_name="",
                    api_key="",
                    base_url="",
                    created_at=None,
                    available_providers=providers
                )
            
            # Existing embedding service
            service = session.query(EmbeddingService).filter(
                EmbeddingService.service_id == service_id,
                EmbeddingService.app_id == app_id
            ).first()
            
            if not service:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Embedding service not found"
                )
            
            # Get available providers for the form
            providers = [{"value": p.value, "name": p.value} for p in EmbeddingProvider]
            
            return EmbeddingServiceDetailSchema(
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
            detail=f"Error retrieving embedding service: {str(e)}"
        )


@embedding_services_router.post("/{service_id}",
                                summary="Create or update embedding service",
                                tags=["Embedding Services"],
                                response_model=EmbeddingServiceDetailSchema)
async def create_or_update_embedding_service(
    app_id: int,
    service_id: int,
    service_data: CreateUpdateEmbeddingServiceSchema,
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Create a new embedding service or update an existing one.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.embedding_service import EmbeddingService
        from datetime import datetime
        
        session = SessionLocal()
        try:
            if service_id == 0:
                # Create new embedding service
                service = EmbeddingService()
                service.app_id = app_id
                service.create_date = datetime.now()
            else:
                # Update existing embedding service
                service = session.query(EmbeddingService).filter(
                    EmbeddingService.service_id == service_id,
                    EmbeddingService.app_id == app_id
                ).first()
                
                if not service:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Embedding service not found"
                    )
            
            # Update service data
            service.name = service_data.name
            service.provider = service_data.provider
            service.description = service_data.model_name
            service.api_key = service_data.api_key
            service.endpoint = service_data.base_url
            
            session.add(service)
            session.commit()
            session.refresh(service)
            
            # Return updated service (reuse the GET logic)
            return await get_embedding_service(app_id, service.service_id, current_user)
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating embedding service: {str(e)}"
        )


@embedding_services_router.delete("/{service_id}",
                                  summary="Delete embedding service",
                                  tags=["Embedding Services"])
async def delete_embedding_service(app_id: int, service_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Delete an embedding service.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.embedding_service import EmbeddingService
        
        session = SessionLocal()
        try:
            service = session.query(EmbeddingService).filter(
                EmbeddingService.service_id == service_id,
                EmbeddingService.app_id == app_id
            ).first()
            
            if not service:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Embedding service not found"
                )
            
            session.delete(service)
            session.commit()
            
            return {"message": "Embedding service deleted successfully"}
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting embedding service: {str(e)}"
        ) 