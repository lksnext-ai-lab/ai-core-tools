"""Service for managing platform-level AI Services (OMNIADMIN only)."""
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from models.system_ai_service import SystemAIService
from repositories.system_ai_service_repository import SystemAIServiceRepository
from repositories.subscription_repository import SubscriptionRepository
from utils.logger import get_logger

logger = get_logger(__name__)


class SystemAIServiceService:

    @staticmethod
    def get_all(db: Session) -> List[SystemAIService]:
        """Return all system AI services (OMNIADMIN view — includes inactive)."""
        repo = SystemAIServiceRepository(db)
        return repo.get_all()

    @staticmethod
    def get_available_for_user(db: Session, user_id: int) -> List[SystemAIService]:
        """Return active system AI services available to a user.

        Free tier users ONLY see these; Starter/Pro users see both these and their own.
        """
        repo = SystemAIServiceRepository(db)
        return repo.get_active()

    @staticmethod
    def get_by_id(db: Session, service_id: int) -> SystemAIService:
        repo = SystemAIServiceRepository(db)
        svc = repo.get_by_id(service_id)
        if not svc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System AI service not found.")
        return svc

    @staticmethod
    def create(db: Session, name: str, provider: str, model: str, api_key_encrypted: Optional[str] = None, is_active: bool = True) -> SystemAIService:
        repo = SystemAIServiceRepository(db)
        svc = repo.create(name=name, provider=provider, model=model, api_key_encrypted=api_key_encrypted, is_active=is_active)
        db.commit()
        db.refresh(svc)
        return svc

    @staticmethod
    def update(db: Session, service_id: int, **kwargs) -> SystemAIService:
        repo = SystemAIServiceRepository(db)
        svc = repo.update(service_id, **kwargs)
        if not svc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System AI service not found.")
        db.commit()
        db.refresh(svc)
        return svc

    @staticmethod
    def delete(db: Session, service_id: int) -> None:
        repo = SystemAIServiceRepository(db)
        deleted = repo.delete(service_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="System AI service not found.")
        db.commit()
