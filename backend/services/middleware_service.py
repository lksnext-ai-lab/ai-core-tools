from datetime import datetime
from typing import List, Optional

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.middleware import Middleware, MiddlewareType
from services import hitl_approval_service as approvals
from repositories.middleware_repository import MiddlewareRepository
from schemas.middleware_schemas import (
    CreateUpdateMiddlewareSchema,
    MiddlewareDetailSchema,
    MiddlewareListItemSchema,
    parse_middleware_config,
    referenced_ai_service_ids,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class MiddlewareValidationError(ValueError):
    """Business-rule violation the client can fix (mapped to HTTP 422)."""


def _to_detail(mw: Middleware) -> MiddlewareDetailSchema:
    return MiddlewareDetailSchema(
        middleware_id=mw.middleware_id,
        name=mw.name,
        description=mw.description or "",
        middleware_type=mw.middleware_type.value,
        config=mw.config,
        created_at=mw.create_date,
        is_frozen=bool(mw.is_frozen),
    )


class MiddlewareService:
    @staticmethod
    def list_middlewares(db: Session, app_id: int) -> List[MiddlewareListItemSchema]:
        return [_to_detail(mw) for mw in MiddlewareRepository.get_all_by_app_id(db, app_id)]

    @staticmethod
    def get_middleware_detail(db: Session, app_id: int, middleware_id: int) -> Optional[MiddlewareDetailSchema]:
        middleware = MiddlewareRepository.get_by_id_and_app_id(db, middleware_id, app_id)
        return _to_detail(middleware) if middleware else None

    @staticmethod
    def create_or_update_middleware(
        db: Session,
        app_id: int,
        middleware_id: int,
        data: CreateUpdateMiddlewareSchema,
    ) -> Optional[MiddlewareDetailSchema]:
        """Create (middleware_id == 0) or update a middleware in one transaction.

        Returns None when the middleware does not exist in this app.
        Raises MiddlewareValidationError for rule violations the caller can fix.
        """
        if middleware_id == 0:
            middleware = Middleware(app_id=app_id, create_date=datetime.now())
        else:
            middleware = MiddlewareRepository.get_by_id_and_app_id(db, middleware_id, app_id)
            if not middleware:
                return None
            if middleware.middleware_type != data.middleware_type:
                raise MiddlewareValidationError("The type of an existing middleware cannot be changed")

        if MiddlewareRepository.name_exists(db, app_id, data.name, exclude_middleware_id=middleware_id):
            raise MiddlewareValidationError(f"A middleware named '{data.name}' already exists in this app")

        # Referenced AI services must belong to this app (tenant isolation).
        config = parse_middleware_config(data.middleware_type, data.config)
        service_ids = referenced_ai_service_ids(data.middleware_type, config)
        if service_ids:
            found = MiddlewareRepository.get_existing_ai_service_ids_for_app(db, service_ids, app_id)
            if set(service_ids) - found:
                raise MiddlewareValidationError("The selected AI service does not exist in this app")

        if (
            middleware_id
            and data.middleware_type == MiddlewareType.HUMAN_IN_THE_LOOP
            and middleware.config != data.config
        ):
            approvals.cancel_pending_for_agents(
                db, [a.agent_id for a in middleware.agent_associations], reason="approval_rules_changed"
            )
        middleware.name = data.name
        middleware.description = data.description or ""
        middleware.middleware_type = data.middleware_type
        middleware.config = data.config
        try:
            MiddlewareRepository.add(db, middleware)
            db.commit()
        except IntegrityError:
            # Concurrent create with the same name hit uq_middleware_app_name.
            db.rollback()
            raise MiddlewareValidationError(f"A middleware named '{data.name}' already exists in this app")
        db.refresh(middleware)
        return _to_detail(middleware)

    @staticmethod
    def names_using_ai_service(db: Session, app_id: int, service_id: int) -> List[str]:
        """Names of the app's middlewares whose config references this AI service."""
        names = []
        types = (MiddlewareType.PII, MiddlewareType.SUMMARIZATION)
        for middleware in MiddlewareRepository.get_by_app_id_and_types(db, app_id, types):
            try:
                config = parse_middleware_config(middleware.middleware_type, middleware.config)
            except ValidationError:
                continue
            if service_id in referenced_ai_service_ids(middleware.middleware_type, config):
                names.append(middleware.name)
        return sorted(names)

    @staticmethod
    def rename_tool_in_approval_rules(db: Session, app_id: Optional[int], old_name: str, new_name: str) -> None:
        """Move human-approval rules to a tool's new name (an agent used as a tool was renamed).

        Without it the rule would keep the old name and the renamed tool would run unapproved.
        Pending approvals of the affected agents are cancelled, as with any rule change.
        """
        if not app_id or old_name == new_name:
            return
        changed = []
        for middleware in MiddlewareRepository.get_by_app_id_and_types(db, app_id, (MiddlewareType.HUMAN_IN_THE_LOOP,)):
            interrupt_on = dict((middleware.config or {}).get("interrupt_on") or {})
            if old_name not in interrupt_on:
                continue
            rule = interrupt_on.pop(old_name)
            interrupt_on.setdefault(new_name, rule)
            middleware.config = {**middleware.config, "interrupt_on": interrupt_on}
            changed.append(middleware)
        if not changed:
            return
        approvals.cancel_pending_for_agents(
            db, [a.agent_id for m in changed for a in m.agent_associations], reason="approval_rules_changed"
        )
        db.commit()
        logger.info("Renamed tool %r to %r in %d approval rule(s) of app %s", old_name, new_name, len(changed), app_id)

    @staticmethod
    def delete_middleware(db: Session, app_id: int, middleware_id: int) -> bool:
        middleware = MiddlewareRepository.get_by_id_and_app_id(db, middleware_id, app_id)
        if not middleware:
            return False
        if middleware.middleware_type == MiddlewareType.HUMAN_IN_THE_LOOP:
            approvals.cancel_pending_for_agents(
                db, [a.agent_id for a in middleware.agent_associations], reason="approval_rules_changed"
            )
        MiddlewareRepository.delete(db, middleware)
        db.commit()
        return True
