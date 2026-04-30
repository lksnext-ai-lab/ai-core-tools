from sqlalchemy.orm import Session
from models.embedding_service import EmbeddingService, EmbeddingProvider
from repositories.embedding_service_repository import EmbeddingServiceRepository
from schemas.embedding_service_schemas import (
    EmbeddingServiceListItemSchema,
    EmbeddingServiceDetailSchema,
    CreateUpdateEmbeddingServiceSchema
)
from core.export_constants import PLACEHOLDER_API_KEY
from utils.secret_utils import mask_api_key, is_masked_key
from typing import List, Optional
from datetime import datetime

class EmbeddingServiceService:

    @staticmethod
    def _to_list_item(service: "EmbeddingService", is_system: bool = False) -> EmbeddingServiceListItemSchema:
        """Convert an EmbeddingService ORM instance to a list item schema."""
        needs_api_key = (
            not service.api_key
            or service.api_key == PLACEHOLDER_API_KEY
        )
        return EmbeddingServiceListItemSchema(
            service_id=service.service_id,
            name=service.name,
            provider=service.provider.value if hasattr(service.provider, 'value') else service.provider,
            model_name=service.description or "",
            created_at=service.create_date,
            needs_api_key=needs_api_key,
            is_system=is_system,
        )

    @staticmethod
    def get_embedding_services_list(db: Session, app_id: int) -> List[EmbeddingServiceListItemSchema]:
        """Get list of embedding services for an app, plus platform-level system services."""
        app_services = EmbeddingServiceRepository.get_by_app_id(db, app_id)
        system_services = EmbeddingServiceRepository.get_system_services(db)

        result = [EmbeddingServiceService._to_list_item(svc, is_system=False) for svc in app_services]
        result += [EmbeddingServiceService._to_list_item(svc, is_system=True) for svc in system_services]
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
            api_key=mask_api_key(service.api_key),
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
        # Only update api_key if user provided a new (non-masked) value
        if not is_masked_key(service_data.api_key):
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

    @staticmethod
    def test_connection_with_config(config: dict) -> dict:
        """Test connection to an embedding service using provided configuration.

        Mirrors :meth:`AIServiceService.test_connection_with_config`: builds an
        embeddings client with the given credentials and runs a single
        ``embed_query`` call. The credentials are NOT persisted.
        """
        from tools.embeddingTools import get_embeddings_model
        from utils.logger import get_logger
        logger = get_logger(__name__)

        api_key = (config.get("api_key") or "").strip()
        provider = config.get("provider") or ""
        model_name = config.get("description") or ""
        endpoint = (config.get("endpoint") or "").strip()

        if not provider:
            return {"status": "error", "message": "Provider is required"}
        if not model_name:
            return {"status": "error", "message": "Model name is required"}

        # Ollama runs locally and may not need an API key; every other
        # provider requires one to talk to its remote endpoint.
        requires_api_key = provider != EmbeddingProvider.Ollama.value
        if requires_api_key and (
            not api_key
            or api_key == PLACEHOLDER_API_KEY
            or is_masked_key(api_key)
        ):
            return {
                "status": "error",
                "message": (
                    "API key is required. Please configure a valid API key "
                    "before testing the connection."
                ),
            }

        class _MockEmbeddingService:
            def __init__(self, data):
                self.provider = data.get("provider")
                self.name = data.get("description")  # embeddingTools uses .name as model
                self.api_key = data.get("api_key")
                self.endpoint = data.get("endpoint")

        try:
            embeddings = get_embeddings_model(_MockEmbeddingService(config))
            embeddings.embed_query("ping")
            return {
                "status": "success",
                "message": "Successfully connected to embedding service.",
            }
        except Exception as e:
            logger.error(
                "Error testing embedding service connection (provider: %s): %s",
                provider,
                str(e),
            )
            return {"status": "error", "message": str(e)}

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