"""Service for importing Middlewares."""

import copy
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pydantic import ValidationError
from sqlalchemy.orm import Session

from core.export_constants import validate_export_version
from models.ai_service import AIService
from models.middleware import Middleware, MiddlewareType
from schemas.export_schemas import ExportMiddlewareSchema, MiddlewareExportFileSchema
from schemas.import_schemas import ComponentType, ConflictMode, ImportSummarySchema
from schemas.middleware_schemas import CreateUpdateMiddlewareSchema, parse_middleware_config
from services.middleware_export_service import AGENT_LLM, AI_SERVICE_CONFIG_PATHS, set_config_ref
from services.middleware_service import MiddlewareService
from utils.logger import get_logger

logger = get_logger(__name__)

NEXT_STEPS = ["Review the imported middleware", "Attach it to agents from their Advanced tab"]


class MiddlewareImportService:
    """Service for importing Middlewares."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_name_and_app(self, name: str, app_id: int) -> Optional[Middleware]:
        return (
            self.session.query(Middleware)
            .filter(Middleware.name == name, Middleware.app_id == app_id)
            .first()
        )

    def import_middleware(
        self,
        export_data: MiddlewareExportFileSchema,
        app_id: int,
        conflict_mode: ConflictMode = ConflictMode.FAIL,
        new_name: Optional[str] = None,
    ) -> ImportSummarySchema:
        """Import a middleware file.

        Raises:
            ValueError: On a name conflict in FAIL mode or an invalid middleware
        """
        validate_export_version(export_data.metadata.export_version)
        return self.import_item(export_data.middleware, app_id, conflict_mode, new_name)

    def import_item(
        self,
        item: ExportMiddlewareSchema,
        app_id: int,
        conflict_mode: ConflictMode = ConflictMode.FAIL,
        new_name: Optional[str] = None,
        ai_service_id_map: Optional[Dict[str, int]] = None,
        reuse_identical: bool = False,
        tool_renames: Optional[Dict[str, str]] = None,
    ) -> ImportSummarySchema:
        """Create (or override) one middleware in the app.

        ``ai_service_id_map`` (name -> id of services imported in the same operation) takes
        precedence over the app's services. ``reuse_identical`` returns an existing middleware
        with the same name, type and config instead of creating a copy (bundled dependencies).
        ``tool_renames`` moves approval rules to the new names of tool agents renamed on import.
        """
        try:
            middleware_type = MiddlewareType(item.middleware_type)
        except ValueError:
            raise ValueError(f"Middleware '{item.name}' has an unknown type '{item.middleware_type}'") from None
        config, warnings = self._resolve_config(item, middleware_type, app_id, ai_service_id_map or {})
        if middleware_type == MiddlewareType.HUMAN_IN_THE_LOOP and tool_renames:
            config["interrupt_on"] = {
                tool_renames.get(tool, tool): rule for tool, rule in (config.get("interrupt_on") or {}).items()
            }
        try:
            config = parse_middleware_config(middleware_type, config).model_dump()
        except ValidationError as exc:
            raise ValueError(f"Middleware '{item.name}' is not valid: {exc.errors()[0]['msg']}") from None

        final_name = item.name
        existing = self.get_by_name_and_app(final_name, app_id)
        target_id = 0
        if existing:
            if reuse_identical and existing.middleware_type == middleware_type and existing.config == config:
                return self._summary(existing.middleware_id, existing.name, conflict_mode, False, True, warnings)
            if conflict_mode == ConflictMode.FAIL:
                raise ValueError(f"Middleware '{final_name}' already exists in app {app_id}")
            if conflict_mode == ConflictMode.OVERRIDE:
                if existing.middleware_type != middleware_type:
                    raise ValueError(
                        f"Middleware '{final_name}' already exists with type "
                        f"'{existing.middleware_type.value}' and cannot be overridden by a '{middleware_type.value}'"
                    )
                target_id = existing.middleware_id
            else:
                final_name = new_name or self._unique_name(item.name, app_id)

        data = CreateUpdateMiddlewareSchema(
            name=final_name, description=item.description or "", middleware_type=middleware_type, config=config
        )
        detail = MiddlewareService.create_or_update_middleware(self.session, app_id, target_id, data)
        logger.info(f"Imported middleware '{detail.name}' (ID: {detail.middleware_id}) into app {app_id}")
        return self._summary(detail.middleware_id, detail.name, conflict_mode, target_id == 0, existing is not None, warnings)

    def import_for_agent(
        self,
        items: List[ExportMiddlewareSchema],
        middleware_names: List[str],
        app_id: int,
        ai_service_id_map: Optional[Dict[str, int]] = None,
        tool_renames: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[int], List[str]]:
        """Import an agent's bundled middlewares; return their ids in the agent's order and warnings."""
        by_name = {item.name: item for item in items}
        ids, warnings = [], []
        for name in middleware_names:
            item = by_name.get(name)
            if item is None:
                existing = self.get_by_name_and_app(name, app_id)
                if existing is None:
                    warnings.append(f"Middleware '{name}' was not in the export and does not exist in the app; skipped")
                    continue
                ids.append(existing.middleware_id)
                continue
            try:
                summary = self.import_item(
                    item, app_id, ConflictMode.RENAME,
                    ai_service_id_map=ai_service_id_map, reuse_identical=True, tool_renames=tool_renames,
                )
            except ValueError as exc:
                warnings.append(str(exc))
                continue
            ids.append(summary.component_id)
            warnings.extend(summary.warnings)
        return ids, warnings

    def _resolve_config(
        self, item: ExportMiddlewareSchema, middleware_type: MiddlewareType, app_id: int, ai_service_id_map: Dict[str, int]
    ) -> Tuple[dict, List[str]]:
        """Point the config's AI service reference at the target app's service with the exported name."""
        config = copy.deepcopy(item.config or {})
        path = AI_SERVICE_CONFIG_PATHS.get(middleware_type)
        if not path or not item.ai_service_name:
            return config, []
        service_id = ai_service_id_map.get(item.ai_service_name)
        if service_id is None:
            service = (
                self.session.query(AIService)
                .filter(AIService.name == item.ai_service_name, AIService.app_id == app_id)
                .first()
            )
            service_id = service.service_id if service else None
        if service_id is None:
            set_config_ref(config, path, AGENT_LLM)
            return config, [
                f"Middleware '{item.name}': AI service '{item.ai_service_name}' not found in this app; "
                "it will use the agent's model until you choose another one"
            ]
        set_config_ref(config, path, f"ai_service:{service_id}")
        return config, []

    def _unique_name(self, name: str, app_id: int) -> str:
        # Middleware names are at most 100 characters; leave room for the suffix.
        base = name[:70]
        date_str = datetime.now().strftime("%Y-%m-%d")
        candidate = f"{base} (imported {date_str})"
        counter = 1
        while self.get_by_name_and_app(candidate, app_id):
            candidate = f"{base} (imported {date_str} {counter})"
            counter += 1
        return candidate

    @staticmethod
    def _summary(
        component_id: int, name: str, mode: ConflictMode, created: bool, conflict: bool, warnings: List[str]
    ) -> ImportSummarySchema:
        return ImportSummarySchema(
            component_type=ComponentType.MIDDLEWARE,
            component_id=component_id,
            component_name=name,
            mode=mode,
            created=created,
            conflict_detected=conflict,
            warnings=warnings,
            next_steps=NEXT_STEPS,
        )
