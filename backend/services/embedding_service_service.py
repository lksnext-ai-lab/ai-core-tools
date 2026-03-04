from sqlalchemy.orm import Session
from models.embedding_service import EmbeddingService, EmbeddingProvider
from repositories.embedding_service_repository import EmbeddingServiceRepository
from schemas.embedding_service_schemas import (
    EmbeddingServiceListItemSchema,
    EmbeddingServiceDetailSchema,
    CreateUpdateEmbeddingServiceSchema
)
from core.export_constants import PLACEHOLDER_API_KEY
from typing import List, Optional
from datetime import datetime

class EmbeddingServiceService:

    @staticmethod
    def get_embedding_services_list(db: Session, app_id: int) -> List[EmbeddingServiceListItemSchema]:
        """Get list of embedding services for an app"""
        embedding_services = EmbeddingServiceRepository.get_by_app_id(db, app_id)
        
        result = []
        for service in embedding_services:
            needs_api_key = (
                not service.api_key
                or service.api_key == PLACEHOLDER_API_KEY
            )
            result.append(EmbeddingServiceListItemSchema(
                service_id=service.service_id,
                name=service.name,
                provider=service.provider.value if hasattr(service.provider, 'value') else service.provider,
                model_name=service.description or "",
                created_at=service.create_date,
                needs_api_key=needs_api_key,
            ))
        
        return result

    @staticmethod
    def get_embedding_service_detail(db: Session, app_id: int, service_id: int) -> Optional[EmbeddingServiceDetailSchema]:
        """Get detailed embedding service information"""
        if service_id == 0:
            # New embedding service
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
        service = EmbeddingServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
        
        if not service:
            return None
        
        # Get available providers for the form
        providers = [{"value": p.value, "name": p.value} for p in EmbeddingProvider]
        
        needs_api_key = (
            not service.api_key
            or service.api_key == PLACEHOLDER_API_KEY
        )
        return EmbeddingServiceDetailSchema(
            service_id=service.service_id,
            name=service.name,
            provider=service.provider.value if hasattr(service.provider, 'value') else service.provider,
            model_name=service.description or "",
            api_key=service.api_key or "",
            base_url=service.endpoint or "",
            created_at=service.create_date,
            available_providers=providers,
            needs_api_key=needs_api_key,
        )

    @staticmethod
    def create_or_update_embedding_service(
        db: Session, 
        app_id: int, 
        service_id: int, 
        service_data: CreateUpdateEmbeddingServiceSchema
    ) -> Optional[EmbeddingService]:
        """Create or update an embedding service"""
        if service_id == 0:
            # Create new embedding service
            service = EmbeddingService()
            service.app_id = app_id
            service.create_date = datetime.now()
        else:
            # Update existing embedding service
            service = EmbeddingServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
            
            if not service:
                return None
        
        # Update service data
        service.name = service_data.name
        service.provider = service_data.provider
        service.description = service_data.model_name
        service.api_key = service_data.api_key
        service.endpoint = service_data.base_url
        
        if service_id == 0:
            return EmbeddingServiceRepository.create(db, service)
        else:
            return EmbeddingServiceRepository.update(db, service)

    @staticmethod
    def delete_embedding_service(db: Session, app_id: int, service_id: int) -> bool:
        """Delete an embedding service"""
        service = EmbeddingServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
        
        if not service:
            return False
        
        EmbeddingServiceRepository.delete(db, service)
        return True

    # Legacy methods for backward compatibility
    @staticmethod
    def get_embedding_services_by_app_id(app_id):
        from db.database import SessionLocal
        session = SessionLocal()
        try:
            return EmbeddingServiceRepository.get_by_app_id(session, app_id)
        finally:
            session.close()

    @staticmethod
    def get_embedding_services():
        from db.database import SessionLocal
        session = SessionLocal()
        try:
            return EmbeddingServiceRepository.get_all(session)
        finally:
            session.close()
    
    @staticmethod
    def get_embedding_service(embedding_service_id):
        from db.database import SessionLocal
        session = SessionLocal()
        try:
            return EmbeddingServiceRepository.get_by_id(session, embedding_service_id)
        finally:
            session.close()
    
    @staticmethod
    def create_embedding_service(embedding_service):
        from db.database import SessionLocal
        session = SessionLocal()
        try:
            return EmbeddingServiceRepository.create(session, embedding_service)
        finally:
            session.close()

    @staticmethod
    def delete_by_app_id(app_id):
        from db.database import SessionLocal
        session = SessionLocal()
        try:
            EmbeddingServiceRepository.delete_by_app_id(session, app_id)
        finally:
            session.close() 