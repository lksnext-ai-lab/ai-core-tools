from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from models.middleware import Middleware, AgentMiddleware, MiddlewareMCP
from models.mcp_config import MCPConfig


class MiddlewareRepository:
    """Repository class for Middleware database operations"""

    @staticmethod
    def get_all_by_app_id(db: Session, app_id: int) -> List[Middleware]:
        """Get all middlewares for a specific app"""
        return db.query(Middleware).options(
            joinedload(Middleware.mcp_associations)
        ).filter(Middleware.app_id == app_id).all()

    @staticmethod
    def get_by_id_and_app_id(db: Session, middleware_id: int, app_id: int) -> Optional[Middleware]:
        """Get a specific middleware by ID and app ID"""
        return db.query(Middleware).options(
            joinedload(Middleware.mcp_associations)
        ).filter(
            Middleware.middleware_id == middleware_id,
            Middleware.app_id == app_id
        ).first()

    @staticmethod
    def name_exists(db: Session, app_id: int, name: str, exclude_middleware_id: int = 0) -> bool:
        """Check whether another middleware in this app already has this name."""
        query = db.query(Middleware).filter(
            Middleware.app_id == app_id,
            Middleware.name == name,
        )
        if exclude_middleware_id:
            query = query.filter(Middleware.middleware_id != exclude_middleware_id)
        return db.query(query.exists()).scalar()

    @staticmethod
    def create(db: Session, middleware: Middleware) -> Middleware:
        """Create a new middleware"""
        db.add(middleware)
        db.commit()
        db.refresh(middleware)
        return middleware

    @staticmethod
    def update(db: Session, middleware: Middleware) -> Middleware:
        """Update an existing middleware"""
        db.add(middleware)
        db.commit()
        db.refresh(middleware)
        return middleware

    @staticmethod
    def delete(db: Session, middleware: Middleware) -> None:
        """Delete a middleware"""
        db.query(AgentMiddleware).filter(
            AgentMiddleware.middleware_id == middleware.middleware_id
        ).delete(synchronize_session=False)
        db.delete(middleware)
        db.commit()

    @staticmethod
    def delete_by_id_and_app_id(db: Session, middleware_id: int, app_id: int) -> bool:
        """Delete a middleware by ID and app ID"""
        middleware = MiddlewareRepository.get_by_id_and_app_id(db, middleware_id, app_id)
        if middleware:
            MiddlewareRepository.delete(db, middleware)
            return True
        return False

    @staticmethod
    def get_valid_middleware_ids_for_app(db: Session, middleware_ids: set, app_id: int) -> set:
        """Get middleware IDs that exist and belong to the specified app"""
        if not middleware_ids:
            return set()

        valid = db.query(Middleware.middleware_id).filter(
            Middleware.middleware_id.in_(middleware_ids),
            Middleware.app_id == app_id
        ).all()

        return {m.middleware_id for m in valid}

    @staticmethod
    def get_valid_mcp_config_ids_for_app(db: Session, config_ids: List[int], app_id: int) -> List[int]:
        """Get MCPConfig IDs that exist and belong to the specified app"""
        if not config_ids:
            return []

        valid = db.query(MCPConfig.config_id).filter(
            MCPConfig.config_id.in_(config_ids),
            MCPConfig.app_id == app_id
        ).all()

        return [c.config_id for c in valid]

    @staticmethod
    def update_mcp_associations(db: Session, middleware_id: int, config_ids: List[int]) -> None:
        """Replace the MCP associations for a middleware"""
        db.query(MiddlewareMCP).filter(
            MiddlewareMCP.middleware_id == middleware_id
        ).delete(synchronize_session=False)
        for config_id in config_ids:
            db.add(MiddlewareMCP(middleware_id=middleware_id, config_id=config_id))
        db.flush()
