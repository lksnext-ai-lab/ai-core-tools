from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models.ai_service import AIService
from models.embedding_service import EmbeddingService
from models.sandbox_service import SandboxService
from repositories.service_usage_repository import (
    AgentRefs,
    ServiceSnapshot,
    ServiceUsageQueries,
    ServiceUsageRepository,
    SiloRefs,
)
from schemas.middleware_schemas import parse_middleware_config, referenced_ai_service_ids
from schemas.service_lifecycle_schemas import (
    MoveAgentsResponseSchema,
    ServiceLifecycleWarningSchema,
    ServiceUsageAgentSchema,
    ServiceUsageAppSchema,
    ServiceUsageMiddlewareSchema,
    ServiceUsageRepositorySchema,
    ServiceUsageSchema,
    ServiceUsageScheduledTaskSchema,
    ServiceUsageSiloSchema,
    MoveSandboxUsageResponseSchema,
)
from services.middleware_service import MiddlewareService
from services.system_settings_service import SystemSettingsService
from utils.error_handlers import ConflictError, NotFoundError
from utils.error_handlers import ValidationError as AppValidationError
from utils.logger import get_logger
from utils.service_lifecycle import (
    SERVICE_KIND_AI,
    SERVICE_KIND_EMBEDDING,
    SERVICE_KIND_SANDBOX,
    LifecycleStatus,
    compute_lifecycle_status,
    is_retired,
    to_utc,
)

logger = get_logger(__name__)

WARNING_DAYS_SETTING_KEY = "service_end_of_service_warning_days"
DEFAULT_WARNING_DAYS = 30


@dataclass
class LifecycleContext:
    """Everything the warning builders need, loaded once per request.

    ``services`` is keyed by service kind (``ai`` / ``embedding`` / ``sandbox``) and then by service id. The builders only read these dicts, never ORM
    relationships, so building warnings for N resources costs no extra queries.
    """

    warning_days: int
    now: datetime
    services: Dict[str, Dict[int, ServiceSnapshot]] = field(default_factory=dict)
    silos: Dict[int, SiloRefs] = field(default_factory=dict)
    # middleware_id -> (name, AI service ids it references)
    middlewares: Dict[int, Tuple[str, List[int]]] = field(default_factory=dict)
    agent_middlewares: Dict[int, List[int]] = field(default_factory=dict)
    agent_refs: Dict[int, AgentRefs] = field(default_factory=dict)
    app_default_sandbox_service_id: Optional[int] = None


class ServiceLifecycleService:
    """DB-aware parts of the service end-of-service lifecycle (the pure rules live in
    ``utils.service_lifecycle``)."""

    @staticmethod
    def warning_days(db: Session) -> int:
        """Days before end of service during which a service is shown as deprecated.

        Read once per request by callers. Falls back to 30 if the setting cannot be read,
        and clamps negative values to 0.
        """
        try:
            value = SystemSettingsService(db).get_setting(WARNING_DAYS_SETTING_KEY)
            days = DEFAULT_WARNING_DAYS if value is None else int(value)
        except Exception as exc:
            if isinstance(exc, SQLAlchemyError):
                # Leave the caller's session usable for the rest of the request.
                db.rollback()
            logger.warning("Could not read %s, using %s: %s", WARNING_DAYS_SETTING_KEY, DEFAULT_WARNING_DAYS, exc)
            return DEFAULT_WARNING_DAYS
        if days < 0:
            logger.warning("%s is negative (%s), using 0", WARNING_DAYS_SETTING_KEY, days)
            return 0
        return days

    @staticmethod
    def log_change(
        service: Any, kind: str, old: Optional[datetime], new: Optional[datetime], actor_id: Optional[int]
    ) -> None:
        """INFO audit line for an end-of-service date change."""
        logger.info(
            "service_lifecycle.updated kind=%s service_id=%s app_id=%s actor_id=%s old=%s new=%s",
            kind,
            service.service_id,
            service.app_id,
            actor_id,
            old.isoformat() if old else None,
            new.isoformat() if new else None,
        )

    @staticmethod
    def apply_lifecycle_fields(service: Any, kind: str, data: Any, actor_id: Optional[int] = None) -> None:
        """Copy the lifecycle fields present in ``data`` (a pydantic model) onto ``service``.

        A field absent from ``data.model_fields_set`` is left untouched; an explicit null clears it.
        Logs at INFO when the date changes on an already persisted service (creates are logged by
        the caller once the row has an id, via ``log_change``).
        """
        fields_set = data.model_fields_set
        old = to_utc(service.end_of_service_at)
        if "end_of_service_at" in fields_set:
            service.end_of_service_at = to_utc(data.end_of_service_at)
        if "deprecation_notice" in fields_set:
            service.deprecation_notice = data.deprecation_notice
        new = to_utc(service.end_of_service_at)
        if old != new and service.service_id is not None:
            ServiceLifecycleService.log_change(service, kind, old, new, actor_id)

    # ==================== Dependency warnings (AD-8) ====================

    @staticmethod
    def build_context(
        db: Session, app_id: int, agent_ids: Optional[Iterable[int]] = None, all_agents: bool = False
    ) -> LifecycleContext:
        """Load the lookup context for warnings in one fixed set of queries.

        Always: the warning-days setting, AI, embedding and sandbox services, the app's default sandbox, the app's silos. Agent data
        (service references, middleware links, middlewares) is loaded only when ``all_agents`` is
        true (every agent of the app, for list endpoints) or ``agent_ids`` is non-empty. The count
        does not depend on how many agents/silos are involved.
        """
        ids: Optional[List[int]] = None
        if not all_agents:
            ids = sorted({i for i in (agent_ids or []) if i})
        needs_agents = all_agents or bool(ids)
        warning_days = ServiceLifecycleService.warning_days(db)
        middlewares: Dict[int, Tuple[str, List[int]]] = {}
        for row in (ServiceUsageRepository.lifecycle_middlewares(db, app_id) if needs_agents else []):
            try:
                config = parse_middleware_config(row.middleware_type, row.config)
            except ValidationError:
                continue  # an invalid stored config references nothing we can resolve
            middlewares[row.middleware_id] = (row.name, referenced_ai_service_ids(config))
        return LifecycleContext(
            warning_days=warning_days,
            now=datetime.now(timezone.utc),
            services={
                SERVICE_KIND_AI: ServiceUsageRepository.ai_service_snapshots(db, app_id),
                SERVICE_KIND_EMBEDDING: ServiceUsageRepository.embedding_service_snapshots(db, app_id),
                SERVICE_KIND_SANDBOX: ServiceUsageRepository.sandbox_service_snapshots(db, app_id),
            },
            app_default_sandbox_service_id=ServiceUsageRepository.app_default_sandbox_service_id(db, app_id),
            silos=ServiceUsageRepository.silo_refs(db, app_id),
            middlewares=middlewares,
            agent_middlewares=(
                ServiceUsageRepository.agent_middleware_ids(db, app_id, ids) if needs_agents else {}
            ),
            agent_refs=ServiceUsageRepository.agent_refs(db, app_id, ids) if needs_agents else {},
        )

    @staticmethod
    def option_fields(service: Any, warning_days: int) -> Dict[str, Any]:
        """Lifecycle data carried by a service option in a selection dropdown."""
        eos = getattr(service, "end_of_service_at", None)
        return {
            "end_of_service_at": to_utc(eos),
            "deprecation_notice": getattr(service, "deprecation_notice", None),
            "lifecycle_status": compute_lifecycle_status(eos, warning_days).value,
        }

    @staticmethod
    def _entry(
        ctx: LifecycleContext, kind: str, service_id: Optional[int], role: str, via: Optional[str] = None
    ) -> Optional[ServiceLifecycleWarningSchema]:
        if service_id is None:
            return None
        snapshot = ctx.services.get(kind, {}).get(service_id)
        if snapshot is None or snapshot.end_of_service_at is None:
            return None
        status = compute_lifecycle_status(snapshot.end_of_service_at, ctx.warning_days, ctx.now)
        if status is LifecycleStatus.ACTIVE:
            return None
        return ServiceLifecycleWarningSchema(
            service_id=snapshot.service_id,
            service_name=snapshot.name,
            kind=kind,
            role=role,
            via=via,
            lifecycle_status=status.value,
            end_of_service_at=to_utc(snapshot.end_of_service_at),
            deprecation_notice=snapshot.deprecation_notice,
        )

    @staticmethod
    def _finish(entries: Iterable[Optional[ServiceLifecycleWarningSchema]]) -> List[ServiceLifecycleWarningSchema]:
        """Drop empties and duplicates, retired first, then by end-of-service date."""
        unique: Dict[Tuple[int, str, str, Optional[str]], ServiceLifecycleWarningSchema] = {}
        for entry in entries:
            if entry is not None:
                unique.setdefault((entry.service_id, entry.kind, entry.role, entry.via), entry)
        return sorted(
            unique.values(),
            key=lambda e: (0 if e.lifecycle_status == LifecycleStatus.RETIRED.value else 1, e.end_of_service_at),
        )

    @staticmethod
    def warnings_for_agent(agent_row: Any, ctx: LifecycleContext) -> List[ServiceLifecycleWarningSchema]:
        """Warnings for the services an agent depends on.

        ``agent_row`` only needs the service-id attributes (an ``AgentRefs`` or a loaded agent); the
        linked silo and middlewares are resolved through the context dicts.
        """
        if agent_row is None:
            return []
        entry = ServiceLifecycleService._entry
        ai, emb = SERVICE_KIND_AI, SERVICE_KIND_EMBEDDING
        entries = [
            entry(ctx, ai, getattr(agent_row, "service_id", None), "llm"),
            entry(ctx, ai, getattr(agent_row, "vision_service_id", None), "ocr_vision"),
            entry(ctx, ai, getattr(agent_row, "transcription_service_id", None), "transcription"),
            entry(ctx, ai, getattr(agent_row, "video_ai_service_id", None), "video"),
            entry(ctx, emb, getattr(agent_row, "media_embedding_service_id", None), "media_embedding"),
        ]
        silo = ctx.silos.get(getattr(agent_row, "silo_id", None))
        if silo is not None:
            entries.append(entry(ctx, emb, silo.embedding_service_id, "silo_embedding", silo.name))
        for middleware_id in ctx.agent_middlewares.get(getattr(agent_row, "agent_id", None), []):
            name, service_ids = ctx.middlewares.get(middleware_id, (None, []))
            entries.extend(entry(ctx, ai, service_id, "middleware", name) for service_id in service_ids)
        if getattr(agent_row, "enable_code_interpreter", False):
            own = getattr(agent_row, "sandbox_service_id", None)
            if own is not None:
                entries.append(entry(ctx, SERVICE_KIND_SANDBOX, own, "sandbox"))
            else:
                entries.append(entry(
                    ctx, SERVICE_KIND_SANDBOX, ctx.app_default_sandbox_service_id, "sandbox", "app default"))
        return ServiceLifecycleService._finish(entries)

    @staticmethod
    def warnings_for_silo(silo_id: Optional[int], ctx: LifecycleContext) -> List[ServiceLifecycleWarningSchema]:
        """Warnings for the embedding, transcription and video services of a silo."""
        silo = ctx.silos.get(silo_id)
        if silo is None:
            return []
        entry = ServiceLifecycleService._entry
        return ServiceLifecycleService._finish([
            entry(ctx, SERVICE_KIND_EMBEDDING, silo.embedding_service_id, "embedding"),
            entry(ctx, SERVICE_KIND_AI, silo.transcription_service_id, "transcription"),
            entry(ctx, SERVICE_KIND_AI, silo.video_ai_service_id, "video"),
        ])

    @staticmethod
    def warnings_for_task(task: Any, ctx: LifecycleContext) -> List[ServiceLifecycleWarningSchema]:
        """A scheduled task depends on what its agent depends on."""
        return ServiceLifecycleService.warnings_for_agent(ctx.agent_refs.get(getattr(task, "agent_id", None)), ctx)

    # ==================== "Used by" and bulk move (AD-10) ====================

    _USAGE_MODELS = {
        SERVICE_KIND_AI: AIService,
        SERVICE_KIND_EMBEDDING: EmbeddingService,
        SERVICE_KIND_SANDBOX: SandboxService,
    }

    @staticmethod
    def agent_roles(row: Any, kind: str, service_id: int, embedding_silo_ids: Optional[set] = None) -> List[str]:
        """Roles in which an agent row uses the service, in a stable order."""
        roles: List[str] = []
        if kind == SERVICE_KIND_SANDBOX:
            if getattr(row, "sandbox_service_id", None) == service_id:
                roles.append("sandbox")
            elif getattr(row, "sandbox_service_id", None) is None and getattr(row, "enable_code_interpreter", False):
                roles.append("sandbox_app_default")
            return roles
        if kind == SERVICE_KIND_AI:
            for attr, role in (
                ("service_id", "llm"),
                ("vision_service_id", "ocr_vision"),
                ("transcription_service_id", "transcription"),
                ("video_ai_service_id", "video"),
            ):
                if getattr(row, attr, None) == service_id:
                    roles.append(role)
        else:
            if getattr(row, "media_embedding_service_id", None) == service_id:
                roles.append("media_embedding")
            if row.silo_id is not None and row.silo_id in (embedding_silo_ids or set()):
                roles.append("silo_embedding")
        return roles

    @staticmethod
    def silo_roles(row: Any, kind: str, service_id: int) -> List[str]:
        """Roles in which a silo uses the service."""
        if kind == SERVICE_KIND_EMBEDDING:
            return ["embedding"] if row.embedding_service_id == service_id else []
        roles = []
        if row.transcription_service_id == service_id:
            roles.append("transcription")
        if row.video_ai_service_id == service_id:
            roles.append("video")
        return roles

    @staticmethod
    def get_usage(
        db: Session, kind: str, service_id: int, app_id: Optional[int]
    ) -> Optional[ServiceUsageSchema]:
        """Everything that depends on an AI / embedding service, or ``None`` (-> 404) when the caller may not see it.

        ``app_id`` set (app scope): the service must be the app's or a system one, and only that
        app's resources are listed. ``app_id=None`` (platform-admin scope): the service must be a
        system service, resources are listed across apps with their app name.
        """
        model = ServiceLifecycleService._USAGE_MODELS.get(kind)
        if model is None:
            raise ValueError(f"Unsupported service kind: {kind}")
        snapshot = ServiceUsageQueries.service_snapshot(db, model, service_id)
        if snapshot is None:
            return None
        if app_id is None:
            if snapshot.app_id is not None:
                return None
        elif snapshot.app_id is not None and snapshot.app_id != app_id:
            return None

        warning_days = ServiceLifecycleService.warning_days(db)
        q = ServiceUsageQueries
        apps_default: List[ServiceUsageAppSchema] = []
        if kind == SERVICE_KIND_SANDBOX:
            agents, silos, repos = q.sandbox_agents(db, service_id, app_id), [], []
            tasks = q.sandbox_tasks(db, service_id, app_id)
            embedding_silo_ids = set()
            apps_default = [
                ServiceUsageAppSchema(app_id=a.app_id, app_name=a.app_name)
                for a in q.sandbox_apps(db, service_id, app_id)
            ]
        elif kind == SERVICE_KIND_AI:
            agents, silos = q.ai_agents(db, service_id, app_id), q.ai_silos(db, service_id, app_id)
            repos, tasks = q.ai_repositories(db, service_id, app_id), q.ai_tasks(db, service_id, app_id)
            embedding_silo_ids: set = set()
        else:
            agents, silos = q.embedding_agents(db, service_id, app_id), q.embedding_silos(db, service_id, app_id)
            repos, tasks = q.embedding_repositories(db, service_id, app_id), q.embedding_tasks(db, service_id, app_id)
            embedding_silo_ids = {s.silo_id for s in silos}

        admin = app_id is None

        def name_of(row: Any) -> Optional[str]:
            return row.app_name if admin else None

        middlewares: List[ServiceUsageMiddlewareSchema] = []
        if kind == SERVICE_KIND_AI and not admin:
            # Middleware validation forbids referencing system services, but a system id can still be
            # looked at from an app; the app's own middlewares are checked either way.
            found = MiddlewareService.using_ai_service(db, app_id, service_id)
            attached = q.middleware_agent_ids(db, app_id, [m.middleware_id for m in found])
            middlewares = [
                ServiceUsageMiddlewareSchema(
                    middleware_id=m.middleware_id,
                    name=m.name,
                    middleware_type=getattr(m.middleware_type, "value", str(m.middleware_type)),
                    agent_ids=attached.get(m.middleware_id, []),
                    app_id=m.app_id,
                )
                for m in found
            ]

        agent_items = []
        for row in agents:
            roles = ServiceLifecycleService.agent_roles(row, kind, service_id, embedding_silo_ids)
            if roles:
                agent_items.append(ServiceUsageAgentSchema(
                    agent_id=row.agent_id, name=row.name, roles=roles, app_id=row.app_id, app_name=name_of(row)))
        silo_items = [
            ServiceUsageSiloSchema(
                silo_id=r.silo_id, name=r.name, roles=ServiceLifecycleService.silo_roles(r, kind, service_id),
                app_id=r.app_id, app_name=name_of(r))
            for r in silos
        ]
        return ServiceUsageSchema(
            service_id=snapshot.service_id,
            service_name=snapshot.name,
            kind=kind,
            is_system=snapshot.app_id is None,
            lifecycle_status=compute_lifecycle_status(snapshot.end_of_service_at, warning_days).value,
            end_of_service_at=to_utc(snapshot.end_of_service_at),
            deprecation_notice=snapshot.deprecation_notice,
            agents=agent_items,
            silos=silo_items,
            repositories=[
                ServiceUsageRepositorySchema(
                    repository_id=r.repository_id, name=r.name or "", silo_id=r.silo_id, app_id=r.app_id,
                    app_name=name_of(r))
                for r in repos
            ],
            middlewares=middlewares,
            scheduled_tasks=[
                ServiceUsageScheduledTaskSchema(
                    task_id=r.task_id, name=r.name, agent_id=r.agent_id, app_id=r.app_id, app_name=name_of(r))
                for r in tasks
            ],
            apps_using_as_default=apps_default,
        )

    @staticmethod
    def _visible_ai_service(db: Session, app_id: int, service_id: int) -> Optional[ServiceSnapshot]:
        snapshot = ServiceUsageQueries.service_snapshot(db, AIService, service_id)
        if snapshot is None or (snapshot.app_id is not None and snapshot.app_id != app_id):
            return None
        return snapshot

    @staticmethod
    def validate_auto_move_target(
        db: Session, app_id: int, source_service_id: Optional[int], end_of_service_at: Optional[datetime],
        target_service_id: Optional[int], now: Optional[datetime] = None,
    ) -> None:
        """Ensure an automatic agent migration points to a visible service that outlives its source."""
        if target_service_id is None:
            return
        if end_of_service_at is None:
            raise AppValidationError("Set an end-of-service date to schedule an automatic migration", "auto_move_to_service_id")
        if source_service_id is not None and target_service_id == source_service_id:
            raise AppValidationError("The target service must be different from the source service", "auto_move_to_service_id")

        target = ServiceLifecycleService._visible_ai_service(db, app_id, target_service_id)
        if target is None:
            raise AppValidationError("Target AI service not found", "auto_move_to_service_id")
        if is_retired(target, now):
            raise AppValidationError("The target AI service is retired and cannot be selected", "auto_move_to_service_id")
        target_end = to_utc(target.end_of_service_at)
        source_end = to_utc(end_of_service_at)
        if target_end is not None and source_end is not None and target_end <= source_end:
            raise AppValidationError(
                "The target AI service must remain active after the source service ends",
                "auto_move_to_service_id",
            )

    @staticmethod
    def validate_auto_move_dependents(
        db: Session, target_service_id: int, end_of_service_at: Optional[datetime]
    ) -> None:
        """Prevent ending a target service before any source service scheduled to move into it."""
        target_end = to_utc(end_of_service_at)
        if target_end is None:
            return
        dependents = db.execute(
            select(AIService.name, AIService.end_of_service_at).where(
                AIService.auto_move_to_service_id == target_service_id
            )
        ).all()
        if target_end <= datetime.now(timezone.utc) and dependents:
            raise AppValidationError(
                "Cannot retire this service while it is the destination of scheduled migrations",
                "end_of_service_at",
            )
        for name, source_end in dependents:
            source_end_utc = to_utc(source_end)
            if source_end_utc is not None and target_end <= source_end_utc:
                raise AppValidationError(
                    f"Cannot end this service before the scheduled migration from '{name}'",
                    "end_of_service_at",
                )

    @staticmethod
    def _visible_sandbox_service(db: Session, app_id: int, service_id: int) -> Optional[ServiceSnapshot]:
        snapshot = ServiceUsageQueries.service_snapshot(db, SandboxService, service_id)
        if snapshot is None or (snapshot.app_id is not None and snapshot.app_id != app_id):
            return None
        return snapshot

    @staticmethod
    def move_agents(
        db: Session,
        app_id: int,
        source_service_id: int,
        target_service_id: int,
        expected_count: Optional[int],
        actor_id: Optional[int],
    ) -> MoveAgentsResponseSchema:
        """Point every agent of the app that uses ``source`` as its text model at ``target``.

        Raises:
            NotFoundError: the source is not an AI service of the app or a system one.
            AppValidationError: the target is the source, not visible to the app, or retired.
            ConflictError: ``expected_count`` differs from the current number of agents (nothing changes).
        """
        if ServiceLifecycleService._visible_ai_service(db, app_id, source_service_id) is None:
            raise NotFoundError("AI service not found", "ai_service")
        if target_service_id == source_service_id:
            raise AppValidationError("The target service must be different from the source service", "target_service_id")
        target = ServiceLifecycleService._visible_ai_service(db, app_id, target_service_id)
        if target is None:
            raise AppValidationError("Target AI service not found", "target_service_id")
        if is_retired(target):
            raise AppValidationError("The target AI service is retired and cannot be selected", "target_service_id")

        try:
            moved = ServiceUsageQueries.move_agents(db, app_id, source_service_id, target_service_id)
            if expected_count is not None and len(moved) != expected_count:
                db.rollback()
                raise ConflictError(
                    f"The number of agents using this service changed (now {len(moved)}); review and confirm again",
                    "MOVE_COUNT_MISMATCH",
                )
            db.commit()
        except ConflictError:
            raise
        except Exception:
            db.rollback()
            raise
        logger.info(
            "service_lifecycle.agents_moved app_id=%s actor_id=%s source=%s target=%s count=%s",
            app_id, actor_id, source_service_id, target_service_id, len(moved),
        )
        return MoveAgentsResponseSchema(moved_agent_ids=moved, count=len(moved))

    @staticmethod
    def move_sandbox_usage(
        db: Session,
        app_id: int,
        source_service_id: int,
        target_service_id: int,
        expected_agent_count: int,
        expected_app_count: int,
        actor_id: Optional[int],
    ) -> MoveSandboxUsageResponseSchema:
        """Move direct agent references and the app default from one sandbox service to another."""
        if ServiceLifecycleService._visible_sandbox_service(db, app_id, source_service_id) is None:
            raise NotFoundError("Sandbox service not found", "sandbox_service")
        if target_service_id == source_service_id:
            raise AppValidationError("The target service must be different from the source service", "target_service_id")

        target = ServiceLifecycleService._visible_sandbox_service(db, app_id, target_service_id)
        if target is None:
            raise AppValidationError("Target sandbox service not found", "target_service_id")
        if is_retired(target):
            raise AppValidationError("The target sandbox service is retired and cannot be selected", "target_service_id")

        try:
            moved_agent_ids, updated_app_ids = ServiceUsageQueries.move_sandbox_usage(
                db, app_id, source_service_id, target_service_id
            )
            if (
                len(moved_agent_ids) != expected_agent_count
                or len(updated_app_ids) != expected_app_count
            ):
                db.rollback()
                raise ConflictError(
                    "sandbox usage changed "
                    f"(agents now {len(moved_agent_ids)}, apps using it as default now {len(updated_app_ids)}); "
                    "review and confirm again",
                    "MOVE_COUNT_MISMATCH",
                )
            db.commit()
        except ConflictError:
            raise
        except Exception:
            db.rollback()
            raise

        logger.info(
            "service_lifecycle.sandbox_usage_moved app_id=%s actor_id=%s source=%s target=%s agents=%s apps=%s",
            app_id,
            actor_id,
            source_service_id,
            target_service_id,
            len(moved_agent_ids),
            len(updated_app_ids),
        )
        return MoveSandboxUsageResponseSchema(
            moved_agent_ids=moved_agent_ids,
            updated_app_ids=updated_app_ids,
        )
