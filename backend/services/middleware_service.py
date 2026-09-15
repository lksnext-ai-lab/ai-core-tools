from typing import Optional, List
from models.middleware import Middleware, MiddlewareType
from repositories.middleware_repository import MiddlewareRepository
from sqlalchemy.orm import Session
from datetime import datetime
from schemas.middleware_schemas import MiddlewareListItemSchema, MiddlewareDetailSchema, CreateUpdateMiddlewareSchema
from utils.logger import get_logger

logger = get_logger(__name__)


class MiddlewareService:
    @staticmethod
    def list_middlewares(db: Session, app_id: int) -> List[MiddlewareListItemSchema]:
        """Get all middlewares for a specific app as list items"""
        middlewares = MiddlewareRepository.get_all_by_app_id(db, app_id)

        result = []
        for mw in middlewares:
            tool_agent_ids = (mw.config or {}).get('tool_agent_ids', []) if mw.config else []
            result.append(MiddlewareListItemSchema(
                middleware_id=mw.middleware_id,
                name=mw.name,
                description=mw.description or "",
                middleware_type=mw.middleware_type.value if mw.middleware_type else "monitoring",
                config=mw.config,
                created_at=mw.create_date,
                is_frozen=mw.is_frozen or False,
                mcp_config_ids=[a.config_id for a in mw.mcp_associations],
                tool_agent_ids=tool_agent_ids
            ))

        return result

    @staticmethod
    def get_middleware_detail(db: Session, app_id: int, middleware_id: int) -> Optional[MiddlewareDetailSchema]:
        """Get detailed information about a specific middleware"""
        if middleware_id == 0:
            return MiddlewareDetailSchema(
                middleware_id=0,
                name="",
                description="",
                middleware_type="monitoring",
                config=None,
                created_at=None,
                is_frozen=False
            )

        middleware = MiddlewareRepository.get_by_id_and_app_id(db, middleware_id, app_id)

        if not middleware:
            return None

        tool_agent_ids = (middleware.config or {}).get('tool_agent_ids', []) if middleware.config else []
        return MiddlewareDetailSchema(
            middleware_id=middleware.middleware_id,
            name=middleware.name,
            description=middleware.description or "",
            middleware_type=middleware.middleware_type.value if middleware.middleware_type else "monitoring",
            config=middleware.config,
            created_at=middleware.create_date,
            is_frozen=middleware.is_frozen or False,
            mcp_config_ids=[a.config_id for a in middleware.mcp_associations],
            tool_agent_ids=tool_agent_ids
        )

    @staticmethod
    def create_or_update_middleware(
        db: Session,
        app_id: int,
        middleware_id: int,
        data: CreateUpdateMiddlewareSchema
    ) -> Optional[Middleware]:
        """Create a new middleware or update an existing one"""
        if middleware_id == 0:
            from services.tier_enforcement_service import TierEnforcementService
            TierEnforcementService.check_resource_limit(db, app_id, 'middlewares')

            middleware = Middleware()
            middleware.app_id = app_id
            middleware.create_date = datetime.now()
        else:
            middleware = MiddlewareRepository.get_by_id_and_app_id(db, middleware_id, app_id)
            if not middleware:
                return None

        if MiddlewareRepository.name_exists(db, app_id, data.name, exclude_middleware_id=middleware_id):
            raise ValueError(f"A middleware named '{data.name}' already exists in this app")

        middleware.name = data.name
        middleware.description = data.description
        middleware.config = data.config

        # Validate middleware_type
        try:
            middleware.middleware_type = MiddlewareType(data.middleware_type)
        except ValueError:
            valid_types = [t.value for t in MiddlewareType]
            raise ValueError(
                f"Invalid middleware_type '{data.middleware_type}'. Must be one of: {valid_types}"
            )

        if middleware_id == 0:
            middleware = MiddlewareRepository.create(db, middleware)
        else:
            middleware = MiddlewareRepository.update(db, middleware)

        valid_config_ids = MiddlewareRepository.get_valid_mcp_config_ids_for_app(db, data.mcp_config_ids, app_id)
        MiddlewareRepository.update_mcp_associations(db, middleware.middleware_id, valid_config_ids)
        db.commit()
        return middleware

    @staticmethod
    def delete_middleware(db: Session, app_id: int, middleware_id: int) -> bool:
        """Delete a middleware"""
        return MiddlewareRepository.delete_by_id_and_app_id(db, middleware_id, app_id)
