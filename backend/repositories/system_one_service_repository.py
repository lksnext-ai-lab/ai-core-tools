from typing import List, Optional

from sqlalchemy.orm import Session

from models.system_one_agent import SystemOneAgent
from models.system_one_service import SystemOneService


class SystemOneServiceRepository:

    @staticmethod
    def get_by_app_id(db: Session, app_id: int) -> List[SystemOneService]:
        return db.query(SystemOneService).filter(SystemOneService.app_id == app_id).order_by(SystemOneService.service_id).all()

    @staticmethod
    def get_by_id_and_app_id(db: Session, service_id: int, app_id: int) -> Optional[SystemOneService]:
        return db.query(SystemOneService).filter(
            SystemOneService.service_id == service_id,
            SystemOneService.app_id == app_id,
        ).first()

    @staticmethod
    def create(db: Session, service: SystemOneService) -> SystemOneService:
        db.add(service)
        db.commit()
        db.refresh(service)
        return service

    @staticmethod
    def update(db: Session, service: SystemOneService) -> SystemOneService:
        db.add(service)
        db.commit()
        db.refresh(service)
        return service

    @staticmethod
    def delete(db: Session, service: SystemOneService) -> None:
        db.delete(service)
        db.commit()

    @staticmethod
    def get_agents_using(db: Session, service_id: int) -> List[SystemOneAgent]:
        """Agents that depend on the service (the FK is RESTRICT: it cannot be deleted while any exists)."""
        return db.query(SystemOneAgent).filter(SystemOneAgent.system_one_service_id == service_id).all()
