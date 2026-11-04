"""Column-only lookups used to compute end-of-service dependency warnings without N+1 queries.

Every method issues exactly one statement, whatever the number of rows involved, and selects plain
columns (no ORM entities), so the results stay cheap and detached from the session.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from models.agent import Agent
from models.ai_service import AIService
from models.app import App
from models.embedding_service import EmbeddingService
from models.middleware import AgentMiddleware, Middleware, MiddlewareType
from models.ocr_agent import OCRAgent
from models.repository import Repository
from models.sandbox_service import SandboxService
from models.scheduled_task import ScheduledTask
from models.silo import Silo


@dataclass(frozen=True)
class ServiceSnapshot:
    """The lifecycle-relevant columns of an AI / embedding / sandbox service."""

    service_id: int
    name: str
    app_id: Optional[int]
    end_of_service_at: Optional[datetime]
    deprecation_notice: Optional[str]


@dataclass(frozen=True)
class SiloRefs:
    """The services a silo points at."""

    silo_id: int
    name: str
    embedding_service_id: Optional[int]
    transcription_service_id: Optional[int]
    video_ai_service_id: Optional[int]


@dataclass(frozen=True)
class AgentRefs:
    """The service ids an agent points at (``vision_service_id`` only exists on OCR agents)."""

    agent_id: int
    service_id: Optional[int]
    vision_service_id: Optional[int]
    transcription_service_id: Optional[int]
    video_ai_service_id: Optional[int]
    media_embedding_service_id: Optional[int]
    silo_id: Optional[int]
    sandbox_service_id: Optional[int] = None
    enable_code_interpreter: bool = False


@dataclass(frozen=True)
class MiddlewareRow:
    """Raw middleware row; the config is parsed by the service layer."""

    middleware_id: int
    name: str
    middleware_type: MiddlewareType
    config: Optional[dict]


class ServiceUsageRepository:
    """Read-only, tenant-scoped lookups for lifecycle warnings."""

    @staticmethod
    def _snapshots(db: Session, model, app_id: int) -> Dict[int, ServiceSnapshot]:
        stmt = select(
            model.service_id, model.name, model.app_id, model.end_of_service_at, model.deprecation_notice
        ).where(or_(model.app_id == app_id, model.app_id.is_(None)))
        return {row.service_id: ServiceSnapshot(*row) for row in db.execute(stmt)}

    @staticmethod
    def ai_service_snapshots(db: Session, app_id: int) -> Dict[int, ServiceSnapshot]:
        """AI services visible to the app (its own + system), keyed by id. One query."""
        return ServiceUsageRepository._snapshots(db, AIService, app_id)

    @staticmethod
    def embedding_service_snapshots(db: Session, app_id: int) -> Dict[int, ServiceSnapshot]:
        """Embedding services visible to the app (its own + system), keyed by id. One query."""
        return ServiceUsageRepository._snapshots(db, EmbeddingService, app_id)

    @staticmethod
    def sandbox_service_snapshots(db: Session, app_id: int) -> Dict[int, ServiceSnapshot]:
        """Sandbox services visible to the app (its own + system), keyed by id. One query."""
        return ServiceUsageRepository._snapshots(db, SandboxService, app_id)

    @staticmethod
    def app_default_sandbox_service_id(db: Session, app_id: int) -> Optional[int]:
        """The app's ``default_sandbox_service_id``. One query."""
        return db.execute(select(App.default_sandbox_service_id).where(App.app_id == app_id)).scalar_one_or_none()

    @staticmethod
    def silo_refs(db: Session, app_id: int) -> Dict[int, SiloRefs]:
        """The app's silos with the services they use, keyed by silo id. One query."""
        stmt = select(
            Silo.silo_id, Silo.name, Silo.embedding_service_id, Silo.transcription_service_id,
            Silo.video_ai_service_id,
        ).where(Silo.app_id == app_id)
        return {row.silo_id: SiloRefs(*row) for row in db.execute(stmt)}

    @staticmethod
    def lifecycle_middlewares(db: Session, app_id: int) -> List[MiddlewareRow]:
        """The app's middlewares that can reference an AI service (PII, SUMMARIZATION). One query."""
        stmt = select(
            Middleware.middleware_id, Middleware.name, Middleware.middleware_type, Middleware.config
        ).where(
            Middleware.app_id == app_id,
            Middleware.middleware_type.in_([MiddlewareType.PII, MiddlewareType.SUMMARIZATION]),
        )
        return [MiddlewareRow(*row) for row in db.execute(stmt)]

    @staticmethod
    def agent_middleware_ids(
        db: Session, app_id: int, agent_ids: Optional[Sequence[int]] = None
    ) -> Dict[int, List[int]]:
        """``{agent_id: [middleware_id, ...]}`` for the app's agents. One query.

        ``agent_ids=None`` means every agent of the app (no unbounded IN list); an empty sequence
        runs no query.
        """
        result: Dict[int, List[int]] = {}
        if agent_ids is not None and not agent_ids:
            return result
        stmt = (
            select(AgentMiddleware.agent_id, AgentMiddleware.middleware_id)
            .join(Agent, Agent.agent_id == AgentMiddleware.agent_id)
            .where(Agent.app_id == app_id)
        )
        if agent_ids is not None:
            stmt = stmt.where(AgentMiddleware.agent_id.in_(list(agent_ids)))
        for agent_id, middleware_id in db.execute(stmt):
            result.setdefault(agent_id, []).append(middleware_id)
        return result

    @staticmethod
    def agent_refs(db: Session, app_id: int, agent_ids: Optional[Iterable[int]] = None) -> Dict[int, AgentRefs]:
        """Service ids of the app's agents (OCR vision service included). One query.

        ``agent_ids=None`` means every agent of the app; an empty iterable runs no query.
        """
        ids = None if agent_ids is None else list(agent_ids)
        if ids is not None and not ids:
            return {}
        # The OCRAgent *table* is joined directly: joining the mapped subclass would drag the Agent table in twice.
        ocr = OCRAgent.__table__
        stmt = (
            select(
                Agent.agent_id, Agent.service_id, ocr.c.vision_service_id, Agent.transcription_service_id,
                Agent.video_ai_service_id, Agent.media_embedding_service_id, Agent.silo_id,
                Agent.sandbox_service_id, Agent.enable_code_interpreter,
            )
            .select_from(Agent)
            .outerjoin(ocr, ocr.c.agent_id == Agent.agent_id)
            .where(Agent.app_id == app_id)
        )
        if ids is not None:
            stmt = stmt.where(Agent.agent_id.in_(ids))
        return {row.agent_id: AgentRefs(*row) for row in db.execute(stmt)}


# ==================== "Used by" and bulk move ====================


@dataclass(frozen=True)
class UsageAgentRow:
    """An agent that points at the service, with the raw reference columns (roles are computed by the service)."""

    agent_id: int
    name: str
    app_id: int
    app_name: Optional[str]
    service_id: Optional[int]
    vision_service_id: Optional[int]
    transcription_service_id: Optional[int]
    video_ai_service_id: Optional[int]
    media_embedding_service_id: Optional[int]
    silo_id: Optional[int]
    sandbox_service_id: Optional[int] = None
    enable_code_interpreter: bool = False


@dataclass(frozen=True)
class UsageSiloRow:
    silo_id: int
    name: str
    app_id: int
    app_name: Optional[str]
    embedding_service_id: Optional[int]
    transcription_service_id: Optional[int]
    video_ai_service_id: Optional[int]


@dataclass(frozen=True)
class UsageRepositoryRow:
    repository_id: int
    name: Optional[str]
    silo_id: int
    app_id: int
    app_name: Optional[str]


@dataclass(frozen=True)
class UsageTaskRow:
    task_id: int
    name: str
    agent_id: int
    app_id: int
    app_name: Optional[str]


@dataclass(frozen=True)
class UsageAppRow:
    app_id: int
    app_name: str


class ServiceUsageQueries:
    """"Used by" lookups. ``app_id`` set -> only that app's rows (tenant scope); ``None`` -> every app
    (platform-admin scope). Each method is one statement; ``App`` is joined for the app name."""

    @staticmethod
    def _scope(stmt, model, app_id: Optional[int]):
        return stmt if app_id is None else stmt.where(model.app_id == app_id)

    @staticmethod
    def service_snapshot(db: Session, model, service_id: int) -> Optional[ServiceSnapshot]:
        """Lifecycle columns of one AI / embedding service, whichever app owns it."""
        row = db.execute(
            select(model.service_id, model.name, model.app_id, model.end_of_service_at, model.deprecation_notice)
            .where(model.service_id == service_id)
        ).first()
        return ServiceSnapshot(*row) if row else None

    @staticmethod
    def _silo_ids_where(condition, app_id: Optional[int]):
        stmt = select(Silo.silo_id).where(condition)
        return ServiceUsageQueries._scope(stmt, Silo, app_id)

    @staticmethod
    def _agents(db: Session, condition, app_id: Optional[int]) -> List[UsageAgentRow]:
        ocr = OCRAgent.__table__
        stmt = (
            select(
                Agent.agent_id, Agent.name, Agent.app_id, App.name.label("app_name"), Agent.service_id,
                ocr.c.vision_service_id, Agent.transcription_service_id, Agent.video_ai_service_id,
                Agent.media_embedding_service_id, Agent.silo_id, Agent.sandbox_service_id,
                Agent.enable_code_interpreter,
            )
            .select_from(Agent)
            .join(App, App.app_id == Agent.app_id)
            .outerjoin(ocr, ocr.c.agent_id == Agent.agent_id)
            .where(condition)
            .order_by(Agent.agent_id)
        )
        return [UsageAgentRow(*r) for r in db.execute(ServiceUsageQueries._scope(stmt, Agent, app_id))]

    @staticmethod
    def _silos(db: Session, condition, app_id: Optional[int]) -> List[UsageSiloRow]:
        stmt = (
            select(
                Silo.silo_id, Silo.name, Silo.app_id, App.name.label("app_name"), Silo.embedding_service_id,
                Silo.transcription_service_id, Silo.video_ai_service_id,
            )
            .join(App, App.app_id == Silo.app_id)
            .where(condition)
            .order_by(Silo.silo_id)
        )
        return [UsageSiloRow(*r) for r in db.execute(ServiceUsageQueries._scope(stmt, Silo, app_id))]

    @staticmethod
    def _repositories(db: Session, silo_condition, app_id: Optional[int]) -> List[UsageRepositoryRow]:
        silo_ids = ServiceUsageQueries._silo_ids_where(silo_condition, app_id)
        stmt = (
            select(Repository.repository_id, Repository.name, Repository.silo_id, Repository.app_id,
                   App.name.label("app_name"))
            .join(App, App.app_id == Repository.app_id)
            .where(Repository.silo_id.in_(silo_ids))
            .order_by(Repository.repository_id)
        )
        return [UsageRepositoryRow(*r) for r in db.execute(ServiceUsageQueries._scope(stmt, Repository, app_id))]

    @staticmethod
    def _tasks(db: Session, agent_condition, app_id: Optional[int]) -> List[UsageTaskRow]:
        agent_ids = ServiceUsageQueries._scope(select(Agent.agent_id).where(agent_condition), Agent, app_id)
        stmt = (
            select(ScheduledTask.id, ScheduledTask.name, ScheduledTask.agent_id, ScheduledTask.app_id,
                   App.name.label("app_name"))
            .join(App, App.app_id == ScheduledTask.app_id)
            .where(ScheduledTask.agent_id.in_(agent_ids))
            .order_by(ScheduledTask.id)
        )
        return [UsageTaskRow(*r) for r in db.execute(ServiceUsageQueries._scope(stmt, ScheduledTask, app_id))]

    # ---- AI service ----

    @staticmethod
    def _ai_agent_condition(service_id: int):
        ocr = OCRAgent.__table__
        return or_(
            Agent.service_id == service_id,
            ocr.c.vision_service_id == service_id,
            Agent.transcription_service_id == service_id,
            Agent.video_ai_service_id == service_id,
        )

    @staticmethod
    def _ai_silo_condition(service_id: int):
        return or_(Silo.transcription_service_id == service_id, Silo.video_ai_service_id == service_id)

    @staticmethod
    def ai_agents(db: Session, service_id: int, app_id: Optional[int]) -> List[UsageAgentRow]:
        return ServiceUsageQueries._agents(db, ServiceUsageQueries._ai_agent_condition(service_id), app_id)

    @staticmethod
    def ai_silos(db: Session, service_id: int, app_id: Optional[int]) -> List[UsageSiloRow]:
        return ServiceUsageQueries._silos(db, ServiceUsageQueries._ai_silo_condition(service_id), app_id)

    @staticmethod
    def ai_repositories(db: Session, service_id: int, app_id: Optional[int]) -> List[UsageRepositoryRow]:
        return ServiceUsageQueries._repositories(db, ServiceUsageQueries._ai_silo_condition(service_id), app_id)

    @staticmethod
    def ai_tasks(db: Session, service_id: int, app_id: Optional[int]) -> List[UsageTaskRow]:
        # The subquery selects from Agent only, so the OCR-table condition is rewritten on Agent ids.
        ocr = OCRAgent.__table__
        ocr_agent_ids = select(ocr.c.agent_id).where(ocr.c.vision_service_id == service_id)
        condition = or_(
            Agent.service_id == service_id,
            Agent.transcription_service_id == service_id,
            Agent.video_ai_service_id == service_id,
            Agent.agent_id.in_(ocr_agent_ids),
        )
        return ServiceUsageQueries._tasks(db, condition, app_id)

    # ---- Embedding service ----

    @staticmethod
    def _embedding_agent_condition(service_id: int, app_id: Optional[int]):
        silo_ids = ServiceUsageQueries._silo_ids_where(Silo.embedding_service_id == service_id, app_id)
        return or_(Agent.media_embedding_service_id == service_id, Agent.silo_id.in_(silo_ids))

    @staticmethod
    def embedding_agents(db: Session, service_id: int, app_id: Optional[int]) -> List[UsageAgentRow]:
        return ServiceUsageQueries._agents(db, ServiceUsageQueries._embedding_agent_condition(service_id, app_id), app_id)

    @staticmethod
    def embedding_silos(db: Session, service_id: int, app_id: Optional[int]) -> List[UsageSiloRow]:
        return ServiceUsageQueries._silos(db, Silo.embedding_service_id == service_id, app_id)

    @staticmethod
    def embedding_repositories(db: Session, service_id: int, app_id: Optional[int]) -> List[UsageRepositoryRow]:
        return ServiceUsageQueries._repositories(db, Silo.embedding_service_id == service_id, app_id)

    @staticmethod
    def embedding_tasks(db: Session, service_id: int, app_id: Optional[int]) -> List[UsageTaskRow]:
        return ServiceUsageQueries._tasks(db, ServiceUsageQueries._embedding_agent_condition(service_id, app_id), app_id)

    # ---- Sandbox service ----

    @staticmethod
    def sandbox_apps(db: Session, service_id: int, app_id: Optional[int]) -> List[UsageAppRow]:
        """Apps whose ``default_sandbox_service_id`` is this service (only ``app_id`` in app scope)."""
        stmt = select(App.app_id, App.name).where(App.default_sandbox_service_id == service_id).order_by(App.app_id)
        if app_id is not None:
            stmt = stmt.where(App.app_id == app_id)
        return [UsageAppRow(*r) for r in db.execute(stmt)]

    @staticmethod
    def _sandbox_agent_condition(service_id: int, app_id: Optional[int]):
        """Agents pointing at the service, or inheriting it from their app's default."""
        default_app_ids = select(App.app_id).where(App.default_sandbox_service_id == service_id)
        return or_(
            Agent.sandbox_service_id == service_id,
            (Agent.sandbox_service_id.is_(None)) & Agent.enable_code_interpreter.is_(True)
            & Agent.app_id.in_(default_app_ids),
        )

    @staticmethod
    def sandbox_agents(db: Session, service_id: int, app_id: Optional[int]) -> List[UsageAgentRow]:
        return ServiceUsageQueries._agents(db, ServiceUsageQueries._sandbox_agent_condition(service_id, app_id), app_id)

    @staticmethod
    def sandbox_tasks(db: Session, service_id: int, app_id: Optional[int]) -> List[UsageTaskRow]:
        return ServiceUsageQueries._tasks(db, ServiceUsageQueries._sandbox_agent_condition(service_id, app_id), app_id)

    # ---- Middlewares (app scope only) ----

    @staticmethod
    def middleware_agent_ids(db: Session, app_id: int, middleware_ids: Sequence[int]) -> Dict[int, List[int]]:
        """``{middleware_id: [agent_id, ...]}`` for the app's agents attached to these middlewares. One query."""
        result: Dict[int, List[int]] = {}
        if not middleware_ids:
            return result
        stmt = (
            select(AgentMiddleware.middleware_id, AgentMiddleware.agent_id)
            .join(Agent, Agent.agent_id == AgentMiddleware.agent_id)
            .where(Agent.app_id == app_id, AgentMiddleware.middleware_id.in_(list(middleware_ids)))
            .order_by(AgentMiddleware.agent_id)
        )
        for middleware_id, agent_id in db.execute(stmt):
            result.setdefault(middleware_id, []).append(agent_id)
        return result

    # ---- Bulk move ----

    @staticmethod
    def count_agents_on_ai_service(db: Session, app_id: int, service_id: int) -> int:
        """Agents of the app whose text model (``Agent.service_id``) is this service."""
        return db.execute(
            select(func.count()).select_from(Agent).where(Agent.app_id == app_id, Agent.service_id == service_id)
        ).scalar_one()

    @staticmethod
    def move_agents(db: Session, app_id: int, source_id: int, target_id: int) -> List[int]:
        """Repoint ``Agent.service_id`` of every agent of the app in ONE statement; returns the moved ids.

        Does not commit. OCR agents live in the Agent table (STI), so their text model moves as well.
        """
        stmt = (
            update(Agent)
            .where(Agent.app_id == app_id, Agent.service_id == source_id)
            .values(service_id=target_id)
            .returning(Agent.agent_id)
            .execution_options(synchronize_session=False)
        )
        return sorted(db.execute(stmt).scalars().all())

    @staticmethod
    def move_sandbox_usage(
        db: Session, app_id: int, source_id: int, target_id: int
    ) -> tuple[List[int], List[int]]:
        """Repoint direct agent sandbox references and the app default in one transaction."""
        move_agents = (
            update(Agent)
            .where(Agent.app_id == app_id, Agent.sandbox_service_id == source_id)
            .values(sandbox_service_id=target_id)
            .returning(Agent.agent_id)
            .execution_options(synchronize_session=False)
        )
        move_apps = (
            update(App)
            .where(App.app_id == app_id, App.default_sandbox_service_id == source_id)
            .values(default_sandbox_service_id=target_id)
            .returning(App.app_id)
            .execution_options(synchronize_session=False)
        )
        moved_agent_ids = sorted(db.execute(move_agents).scalars().all())
        updated_app_ids = sorted(db.execute(move_apps).scalars().all())
        return moved_agent_ids, updated_app_ids
