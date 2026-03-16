from typing import Optional, List
from sqlalchemy.orm import Session
from models.system_ai_service import SystemAIService
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)


class SystemAIServiceRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[SystemAIService]:
        return self.db.query(SystemAIService).order_by(SystemAIService.name).all()

    def get_active(self) -> List[SystemAIService]:
        return self.db.query(SystemAIService).filter(SystemAIService.is_active == True).all()

    def get_by_id(self, service_id: int) -> Optional[SystemAIService]:
        return self.db.query(SystemAIService).filter(SystemAIService.id == service_id).first()

    def create(self, name: str, provider: str, model: str, api_key_encrypted: Optional[str] = None, is_active: bool = True) -> SystemAIService:
        svc = SystemAIService(
            name=name,
            provider=provider,
            model=model,
            api_key_encrypted=api_key_encrypted,
            is_active=is_active,
        )
        self.db.add(svc)
        self.db.flush()
        return svc

    def update(self, service_id: int, **kwargs) -> Optional[SystemAIService]:
        svc = self.get_by_id(service_id)
        if not svc:
            return None
        for field, value in kwargs.items():
            if value is not None and hasattr(svc, field):
                setattr(svc, field, value)
        svc.updated_at = datetime.utcnow()
        self.db.flush()
        return svc

    def delete(self, service_id: int) -> bool:
        svc = self.get_by_id(service_id)
        if not svc:
            return False
        self.db.delete(svc)
        self.db.flush()
        return True
