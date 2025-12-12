from sqlalchemy.orm import Session
from models.ai_service import AIService, ProviderEnum
from repositories.ai_service_repository import AIServiceRepository
from schemas.ai_service_schemas import AIServiceListItemSchema, AIServiceDetailSchema, CreateUpdateAIServiceSchema
from datetime import datetime
from typing import List
from tools.aiServiceTools import create_llm_from_service
from utils.logger import get_logger
import asyncio
from concurrent.futures import TimeoutError as FuturesTimeoutError
from langchain_core.runnables import RunnableConfig

logger = get_logger(__name__)

class AIServiceService:
    
    @staticmethod
    def get_ai_services_by_app_id(db: Session, app_id: int) -> List[AIServiceListItemSchema]:
        """Get all AI services for a specific app"""
        ai_services = AIServiceRepository.get_by_app_id(db, app_id)
        
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
    
    @staticmethod
    def get_ai_service_detail(db: Session, app_id: int, service_id: int) -> AIServiceDetailSchema:
        """Get detailed information about a specific AI service"""
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
        service = AIServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
        
        if not service:
            return None
        
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
    
    @staticmethod
    def create_or_update_ai_service(db: Session, app_id: int, service_id: int, service_data: CreateUpdateAIServiceSchema) -> AIServiceDetailSchema:
        """Create a new AI service or update an existing one"""
        if service_id == 0:
            # Create new AI service
            service = AIService()
            service.app_id = app_id
            service.create_date = datetime.now()
        else:
            # Update existing AI service
            service = AIServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
            
            if not service:
                return None
        
        # Update service data
        service.name = service_data.name
        service.provider = service_data.provider  # Store as string, not enum
        service.description = service_data.model_name  # Store model name in description
        service.api_key = service_data.api_key
        service.endpoint = service_data.base_url  # Store base_url in endpoint
        
        # Create or update the service
        if service_id == 0:
            service = AIServiceRepository.create(db, service)
        else:
            service = AIServiceRepository.update(db, service)
        
        # Return updated service detail
        return AIServiceService.get_ai_service_detail(db, app_id, service.service_id)
    
    @staticmethod
    def copy_ai_service(db: Session, app_id: int, service_id: int) -> AIServiceDetailSchema:
        """Copy an existing AI service"""
        service = AIServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
        
        if not service:
            return None

        existing = {s.name for s in AIServiceService.get_ai_services_by_app_id(db, app_id)}
        base_name = service.name.strip() if service.name else "AI Service"
        new_name = f"{base_name} Copy"
        counter = 2
        while new_name in existing:
            new_name = f"{base_name} Copy {counter}"
            counter += 1

        # Create a new service with the same data
        new_service = AIService(
            app_id=app_id,
            name=new_name,
            provider=service.provider,
            description=service.description,
            api_key=service.api_key,
            endpoint=service.endpoint,
            create_date=datetime.now()
        )
        
        new_service = AIServiceRepository.create(db, new_service)
        
        return AIServiceService.get_ai_service_detail(db, app_id, new_service.service_id)

    @staticmethod
    def delete_ai_service(db: Session, app_id: int, service_id: int) -> bool:
        """Delete an AI service"""
        service = AIServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
        
        if not service:
            return False
        
        AIServiceRepository.delete(db, service)
        
        return True

    @staticmethod
    def test_connection_with_config(config: dict) -> dict:
        """Test connection to AI service using provided configuration"""
        try:
            # Create a mock object that mimics AIService model
            class MockAIService:
                def __init__(self, data):
                    self.provider = data.get('provider')
                    self.description = data.get('description') # Model name
                    self.api_key = data.get('api_key')
                    self.endpoint = data.get('endpoint')
                    self.api_version = data.get('api_version')
            
            service = MockAIService(config)
            
            # Validate required fields
            if not service.provider:
                return {
                    "status": "error",
                    "message": "Provider is required"
                }
            if not service.description:
                return {
                    "status": "error",
                    "message": "Model name is required"
                }
            
            # Build LLM using shared tool
            llm = create_llm_from_service(service, temperature=0)
            
            # Test invocation with timeout
            try:
                # Add timeout to prevent hanging connections
                config_with_timeout = RunnableConfig(timeout=30)
                response = llm.invoke("Hello", config=config_with_timeout)
            except (TimeoutError, FuturesTimeoutError, asyncio.TimeoutError):
                return {
                    "status": "error",
                    "message": "Connection timeout: The AI service did not respond within 30 seconds"
                }
            
            return {
                "status": "success",
                "message": "Successfully connected to AI service.",
                "response": str(response.content) if hasattr(response, 'content') else str(response)
            }
            
        except Exception as e:
            logger.error(f"Error testing AI service connection: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }

    @staticmethod
    def test_connection(db: Session, app_id: int, service_id: int) -> dict:
        """Test connection to AI service"""
        service = AIServiceRepository.get_by_id_and_app_id(db, service_id, app_id)
        if not service:
            return {"status": "error", "message": "AI service not found"}
            
        # Convert model to dict for the shared method
        config = {
            "provider": service.provider,
            "description": service.description,
            "api_key": service.api_key,
            "endpoint": service.endpoint
        }
        
        return AIServiceService.test_connection_with_config(config)
    @staticmethod
    def delete_by_app_id(app_id: int):
        """Delete all AI services for a specific app"""
        from db.database import SessionLocal
        session = SessionLocal()
        try:
            AIServiceRepository.delete_by_app_id(session, app_id)
        finally:
            session.close() 