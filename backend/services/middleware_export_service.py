"""Service for exporting Middlewares."""

import copy
from typing import Dict, List, Optional, Tuple

from models.ai_service import AIService
from models.middleware import Middleware, MiddlewareType
from repositories.middleware_repository import MiddlewareRepository
from schemas.export_schemas import ExportMiddlewareSchema, MiddlewareExportFileSchema
from services.base_export_service import BaseExportService
from utils.logger import get_logger

logger = get_logger(__name__)

# Where each type's config may reference an AI service ("agent_llm" or "ai_service:<id>").
AI_SERVICE_CONFIG_PATHS: Dict[MiddlewareType, Tuple[str, ...]] = {
    MiddlewareType.SUMMARIZATION: ("summarization_model",),
    MiddlewareType.PII: ("llm_detector", "ai_service"),
}
AGENT_LLM = "agent_llm"


def get_config_ref(config: dict, path: Tuple[str, ...]) -> Optional[str]:
    node = config
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, str) else None


def set_config_ref(config: dict, path: Tuple[str, ...], value: str) -> None:
    node = config
    for key in path[:-1]:
        node = node.get(key)
        if not isinstance(node, dict):
            return
    node[path[-1]] = value


class MiddlewareExportService(BaseExportService):
    """Service for exporting Middlewares."""

    def to_export_schema(self, middleware: Middleware) -> ExportMiddlewareSchema:
        """Export one middleware, replacing its AI service reference by the service name."""
        config = copy.deepcopy(middleware.config or {})
        ai_service_name = None
        path = AI_SERVICE_CONFIG_PATHS.get(middleware.middleware_type)
        ref = get_config_ref(config, path) if path else None
        if ref and ref.startswith("ai_service:"):
            service = self.session.get(AIService, int(ref.split(":", 1)[1]))
            if service is not None and service.app_id == middleware.app_id:
                ai_service_name = service.name
            set_config_ref(config, path, AGENT_LLM)
        return ExportMiddlewareSchema(
            name=middleware.name,
            description=middleware.description,
            middleware_type=middleware.middleware_type.value,
            config=config,
            ai_service_name=ai_service_name,
        )

    def export_middleware(
        self, middleware_id: int, app_id: int, user_id: Optional[int] = None
    ) -> MiddlewareExportFileSchema:
        """Export a middleware to its JSON file structure.

        Raises:
            ValueError: If the middleware is not found in the app
        """
        middleware = MiddlewareRepository.get_by_id_and_app_id(self.session, middleware_id, app_id)
        if not middleware:
            raise ValueError(f"Middleware with ID {middleware_id} not found in app {app_id}")
        logger.info(f"Exported middleware '{middleware.name}' (ID: {middleware_id})")
        return MiddlewareExportFileSchema(
            metadata=self.create_metadata(user_id, app_id),
            middleware=self.to_export_schema(middleware),
        )

    def export_all(self, app_id: int) -> List[ExportMiddlewareSchema]:
        return [self.to_export_schema(m) for m in MiddlewareRepository.get_all_by_app_id(self.session, app_id)]

    def export_for_agent(self, agent) -> List[ExportMiddlewareSchema]:
        """The agent's middlewares, in execution order."""
        return [
            self.to_export_schema(assoc.middleware)
            for assoc in (agent.middleware_associations or [])
            if assoc.middleware is not None
        ]
