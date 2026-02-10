from sqlalchemy.orm import Session
from models.ai_service import AIService
from typing import List, Optional

class AIServiceRepository:
    
    @staticmethod
    def get_by_app_id(db: Session, app_id: int) -> List[AIService]:
        """Get all AI services for a specific app"""
        return db.query(AIService).filter(AIService.app_id == app_id).all()
    
    @staticmethod
    def get_by_id(db: Session, service_id: int) -> Optional[AIService]:
        """Get AI service by ID"""
        return db.query(AIService).filter(AIService.service_id == service_id).first()

    @staticmethod
    def get_by_id_and_app_id(db: Session, service_id: int, app_id: int) -> Optional[AIService]:
        """Get a specific AI service by ID and app ID"""
        return db.query(AIService).filter(
            AIService.service_id == service_id,
            AIService.app_id == app_id
        ).first()
    
    @staticmethod
    def create(db: Session, ai_service: AIService) -> AIService:
        """Create a new AI service"""
        db.add(ai_service)
        db.commit()
        db.refresh(ai_service)
        return ai_service
    
    @staticmethod
    def update(db: Session, ai_service: AIService) -> AIService:
        """Update an existing AI service"""
        db.add(ai_service)
        db.commit()
        db.refresh(ai_service)
        return ai_service
    
    @staticmethod
    def delete(db: Session, ai_service: AIService) -> None:
        """Delete an AI service"""
        db.delete(ai_service)
        db.commit()
    
    @staticmethod
    def delete_by_app_id(db: Session, app_id: int) -> None:
        """Delete all AI services for a specific app"""
        db.query(AIService).filter(AIService.app_id == app_id).delete()
        db.commit()
