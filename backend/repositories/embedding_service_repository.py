from sqlalchemy.orm import Session
from models.embedding_service import EmbeddingService
from typing import List, Optional

class EmbeddingServiceRepository:
    
    @staticmethod
    def get_by_app_id(db: Session, app_id: int) -> List[EmbeddingService]:
        """Get all embedding services for a specific app"""
        return db.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).all()
    
    @staticmethod
    def get_by_id_and_app_id(db: Session, service_id: int, app_id: int) -> Optional[EmbeddingService]:
        """Get a specific embedding service by ID and app ID"""
        return db.query(EmbeddingService).filter(
            EmbeddingService.service_id == service_id,
            EmbeddingService.app_id == app_id
        ).first()
    
    @staticmethod
    def get_by_id(db: Session, service_id: int) -> Optional[EmbeddingService]:
        """Get a specific embedding service by ID"""
        return db.query(EmbeddingService).filter(EmbeddingService.service_id == service_id).first()
    
    @staticmethod
    def get_all(db: Session) -> List[EmbeddingService]:
        """Get all embedding services"""
        return db.query(EmbeddingService).all()
    
    @staticmethod
    def create(db: Session, embedding_service: EmbeddingService) -> EmbeddingService:
        """Create a new embedding service"""
        db.add(embedding_service)
        db.commit()
        db.refresh(embedding_service)
        return embedding_service
    
    @staticmethod
    def update(db: Session, embedding_service: EmbeddingService) -> EmbeddingService:
        """Update an existing embedding service"""
        db.add(embedding_service)
        db.commit()
        db.refresh(embedding_service)
        return embedding_service
    
    @staticmethod
    def delete(db: Session, embedding_service: EmbeddingService) -> None:
        """Delete an embedding service"""
        db.delete(embedding_service)
        db.commit()
    
    @staticmethod
    def delete_by_app_id(db: Session, app_id: int) -> None:
        """Delete all embedding services for a specific app"""
        embedding_services = db.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).all()
        for embedding_service in embedding_services:
            db.delete(embedding_service)
        db.commit()
