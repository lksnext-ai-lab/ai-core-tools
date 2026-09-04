from sqlalchemy.orm import Session
from models.sandbox_service import SandboxService
from typing import List, Optional

class SandboxServiceRepository:

    @staticmethod
    def get_by_app_id(db: Session, app_id: int) -> List[SandboxService]:
        """Get all sandbox services for a specific app"""
        return db.query(SandboxService).filter(SandboxService.app_id == app_id).all()

    @staticmethod
    def get_by_id(db: Session, service_id: int) -> Optional[SandboxService]:
        """Get sandbox service by ID"""
        return db.query(SandboxService).filter(SandboxService.service_id == service_id).first()

    @staticmethod
    def get_by_id_and_app_id(db: Session, service_id: int, app_id: int) -> Optional[SandboxService]:
        """Get a specific sandbox service by ID and app ID"""
        return db.query(SandboxService).filter(
            SandboxService.service_id == service_id,
            SandboxService.app_id == app_id
        ).first()

    @staticmethod
    def create(db: Session, sandbox_service: SandboxService) -> SandboxService:
        """Create a new sandbox service"""
        db.add(sandbox_service)
        db.commit()
        db.refresh(sandbox_service)
        return sandbox_service

    @staticmethod
    def update(db: Session, sandbox_service: SandboxService) -> SandboxService:
        """Update an existing sandbox service"""
        db.add(sandbox_service)
        db.commit()
        db.refresh(sandbox_service)
        return sandbox_service

    @staticmethod
    def delete(db: Session, sandbox_service: SandboxService) -> None:
        """Delete a sandbox service"""
        db.delete(sandbox_service)
        db.commit()

    @staticmethod
    def get_system_services(db: Session) -> List[SandboxService]:
        """Return all SandboxService records with no app (system/platform services)."""
        return db.query(SandboxService).filter(SandboxService.app_id.is_(None)).all()

    @staticmethod
    def delete_by_app_id(db: Session, app_id: int) -> None:
        """Delete all sandbox services for a specific app"""
        db.query(SandboxService).filter(SandboxService.app_id == app_id).delete()
        db.commit()
