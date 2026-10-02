from typing import Iterable, List, Optional, Set
from sqlalchemy.orm import Session
from models.middleware import Middleware
from models.ai_service import AIService


class MiddlewareRepository:
    """Data access for Middleware. Callers own the transaction (commit/rollback)."""

    @staticmethod
    def get_all_by_app_id(db: Session, app_id: int) -> List[Middleware]:
        return (
            db.query(Middleware)
            .filter(Middleware.app_id == app_id)
            .order_by(Middleware.name)
            .all()
        )

    @staticmethod
    def get_by_id_and_app_id(db: Session, middleware_id: int, app_id: int) -> Optional[Middleware]:
        return db.query(Middleware).filter(
            Middleware.middleware_id == middleware_id,
            Middleware.app_id == app_id,
        ).first()

    @staticmethod
    def get_by_ids_and_app_id(db: Session, middleware_ids: Iterable[int], app_id: int) -> List[Middleware]:
        ids = set(middleware_ids)
        if not ids:
            return []
        return db.query(Middleware).filter(
            Middleware.middleware_id.in_(ids),
            Middleware.app_id == app_id,
        ).all()

    @staticmethod
    def name_exists(db: Session, app_id: int, name: str, exclude_middleware_id: int = 0) -> bool:
        query = db.query(Middleware).filter(Middleware.app_id == app_id, Middleware.name == name)
        if exclude_middleware_id:
            query = query.filter(Middleware.middleware_id != exclude_middleware_id)
        return db.query(query.exists()).scalar()

    @staticmethod
    def get_existing_ai_service_ids_for_app(db: Session, service_ids: Iterable[int], app_id: int) -> Set[int]:
        ids = set(service_ids)
        if not ids:
            return set()
        rows = db.query(AIService.service_id).filter(
            AIService.service_id.in_(ids),
            AIService.app_id == app_id,
        ).all()
        return {r.service_id for r in rows}

    @staticmethod
    def add(db: Session, middleware: Middleware) -> Middleware:
        db.add(middleware)
        db.flush()
        return middleware

    @staticmethod
    def delete(db: Session, middleware: Middleware) -> None:
        # agent_middlewares rows go with it (ON DELETE CASCADE + passive_deletes).
        db.delete(middleware)
        db.flush()
