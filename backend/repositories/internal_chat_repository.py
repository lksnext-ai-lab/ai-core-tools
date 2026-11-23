"""Data access of the flexible per-App Chat.

Data only: no business rules. Write methods ``flush`` but never ``commit`` (the service owns the
transaction, and the turn-completion hook runs inside a SAVEPOINT that must not be committed from
inside) -- the single exception is :meth:`InternalChatAgentRepository.get_or_create`, which commits
by design so the race loser re-reads the winner's row.
"""
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import and_, exists, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload

from models.agent import (
    AGENT_KIND_INTERNAL_CHAT,
    DEFAULT_AGENT_TEMPERATURE,
    DEFAULT_PROMPT_TEMPLATE,
    Agent,
    MarketplaceVisibility,
)
from models.ai_service import AIService
from models.app import App
from models.conversation import Conversation
from models.domain import Domain
from models.embedding_service import EmbeddingService
from models.internal_chat import ChatConversationState, ChatUserDefault, ConversationTurn
from models.mcp_config import MCPConfig
from models.sandbox_service import SandboxService
from models.repository import PLAYGROUND_MEDIA_REPO_TYPE, TEMP_REPO_PREFIX, Repository
from repositories.silo_repository import SiloRepository
from models.sharepoint_source import SharePointSource
from models.silo import Silo
from models.skill import Skill
from repositories.skill_repository import SkillRepository
from utils.logger import get_logger

logger = get_logger(__name__)

INTERNAL_CHAT_AGENT_NAME = "__internal_chat__"


def set_local_timeouts(db: Session, lock_timeout_ms: int, statement_timeout_ms: int) -> None:
    """Bound lock waits and statement time of the CURRENT TRANSACTION (``SET LOCAL`` semantics).

    ``set_config(name, value, true)`` is the parameterized form of ``SET LOCAL``: the values last until the
    transaction ends (commit or rollback; inside a SAVEPOINT they survive its release but are undone if it
    is rolled back), so they never leak to later transactions of the same session.
    """
    db.execute(select(func.set_config("lock_timeout", str(int(lock_timeout_ms)), True)))
    db.execute(select(func.set_config("statement_timeout", str(int(statement_timeout_ms)), True)))


class InternalChatAgentRepository:
    """The single hidden internal chat agent of an App."""

    @staticmethod
    def get_id(db: Session, app_id: int) -> Optional[int]:
        """Id of the App's internal chat agent, or None when it has not been created yet."""
        return db.execute(
            select(Agent.agent_id).where(Agent.app_id == app_id, Agent.internal_chat_clause())
        ).scalar_one_or_none()

    @staticmethod
    def get_or_create(db: Session, app_id: int, system_prompt: str) -> int:
        """Return the App's internal chat agent id, creating the row when missing.

        ``INSERT .. ON CONFLICT DO NOTHING`` on the partial unique index ``uq_agent_internal_chat_per_app``
        followed by a re-SELECT: concurrent first uses converge on one row and nobody sees an
        ``IntegrityError``. Bypasses the tier agent limit on purpose (the agent is not a user resource).
        Commits (the loser of a race must be able to read the winner's committed row).

        Raises:
            RuntimeError: if the row is still missing after the insert (an invariant violation).
        """
        existing = InternalChatAgentRepository.get_id(db, app_id)
        if existing is not None:
            return existing
        stmt = (
            pg_insert(Agent.__table__)
            .values(
                name=INTERNAL_CHAT_AGENT_NAME,
                description=None,
                type="agent",
                kind=AGENT_KIND_INTERNAL_CHAT,
                status="active",
                app_id=app_id,
                create_date=datetime.now(),
                system_prompt=system_prompt,
                prompt_template=DEFAULT_PROMPT_TEMPLATE,
                temperature=DEFAULT_AGENT_TEMPERATURE,
                has_memory=True,
                service_id=None,
                silo_id=None,
                is_tool=False,
                enable_code_interpreter=False,
                a2a_enabled=False,
                marketplace_visibility=MarketplaceVisibility.UNPUBLISHED,
                skill_router_enabled=False,
                server_tools=[],
                exposed_chat_filters=[],
                rag_fixed_filters=[],
                rag_k=10,
                rag_search_type="similarity",
                rag_max_retrieval_calls=4,
                request_count=0,
                is_frozen=False,
            )
            .on_conflict_do_nothing(index_elements=["app_id"], index_where=text("kind = 'internal_chat'"))
        )
        db.execute(stmt)
        db.commit()
        agent_id = InternalChatAgentRepository.get_id(db, app_id)
        if agent_id is None:
            raise RuntimeError("internal chat agent missing after get-or-create")
        return agent_id


    @staticmethod
    def list_orphan_temp_repository_ids(db: Session, older_than: datetime, limit: int) -> List[int]:
        """Ids of chat temp repositories whose conversation (agent + session) no longer exists.

        Only repositories of the hidden internal-chat agent qualify. ``older_than`` is compared with
        ``Repository.create_date``, which ``RepositoryService.create_repository`` writes with ``datetime.now()``
        (server LOCAL naive time): callers must pass a threshold computed with the same clock, not UTC.
        """
        live = exists().where(
            Conversation.agent_id == Agent.agent_id,
            Repository.name == func.concat(TEMP_REPO_PREFIX, Agent.agent_id, "_", Conversation.session_id),
        )
        return list(
            db.execute(
                select(Repository.repository_id)
                .join(Agent, and_(Agent.app_id == Repository.app_id, Agent.kind == "internal_chat"))
                .where(
                    Repository.type == PLAYGROUND_MEDIA_REPO_TYPE,
                    # Exact prefix compare, NOT LIKE / startswith: ``_`` is a LIKE wildcard, so agent 3's prefix would
                    # also match the temp repositories of agents 30-39, 300-399...
                    func.left(Repository.name, func.length(func.concat(TEMP_REPO_PREFIX, Agent.agent_id, "_")))
                    == func.concat(TEMP_REPO_PREFIX, Agent.agent_id, "_"),
                    Repository.create_date < older_than,
                    ~live,
                )
                .order_by(Repository.repository_id)
                .limit(limit)
            ).scalars().all()
        )


class ConversationTurnRepository:
    """``conversation_turn`` rows (one per completed assistant message)."""

    @staticmethod
    def next_index(db: Session, conversation_id: int) -> int:
        """Next ``turn_index`` of the conversation.

        The caller MUST already hold the ``FOR UPDATE`` lock of the conversation's ``chat_conversation_state``
        row (``ChatConversationStateRepository.lock``): that is what serializes concurrent completions of the
        same conversation, so two of them cannot allocate the same index.
        """
        current = db.execute(
            select(func.coalesce(func.max(ConversationTurn.turn_index), 0)).where(
                ConversationTurn.conversation_id == conversation_id
            )
        ).scalar_one()
        return int(current) + 1

    @staticmethod
    def insert(db: Session, **fields: Any) -> ConversationTurn:
        """Insert a turn row (flush only)."""
        row = ConversationTurn(**fields)
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def list_for_conversation(db: Session, conversation_id: int) -> List[ConversationTurn]:
        """Turns of a conversation in order."""
        return list(
            db.execute(
                select(ConversationTurn)
                .where(ConversationTurn.conversation_id == conversation_id)
                .order_by(ConversationTurn.turn_index)
            ).scalars()
        )

    @staticmethod
    def delete_for_conversation(db: Session, conversation_id: int) -> int:
        """Delete every turn of a conversation (flush only); returns the number of rows."""
        result = db.query(ConversationTurn).filter(ConversationTurn.conversation_id == conversation_id).delete(
            synchronize_session=False
        )
        return int(result or 0)


class ChatUserDefaultRepository:
    """Per ``(user_id, app_id)`` last selection."""

    @staticmethod
    def get(db: Session, user_id: int, app_id: int) -> Optional[Dict[str, Any]]:
        """Stored selection of the user in the App, or None."""
        return db.execute(
            select(ChatUserDefault.selection).where(
                ChatUserDefault.user_id == user_id, ChatUserDefault.app_id == app_id
            )
        ).scalar_one_or_none()

    @staticmethod
    def upsert(db: Session, user_id: int, app_id: int, selection: Dict[str, Any]) -> None:
        """Write the user's default; touches only the ``(user_id, app_id)`` row (``updated_at`` set explicitly)."""
        now = datetime.utcnow()
        stmt = pg_insert(ChatUserDefault.__table__).values(
            user_id=user_id, app_id=app_id, selection=selection, updated_at=now
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["user_id", "app_id"],
                set_={"selection": stmt.excluded.selection, "updated_at": now},
            )
        )


class ChatConversationStateRepository:
    """Current selection of a Chat conversation."""

    @staticmethod
    def get(db: Session, conversation_id: int) -> Optional[Dict[str, Any]]:
        """Stored selection of the conversation, or None."""
        return db.execute(
            select(ChatConversationState.selection).where(ChatConversationState.conversation_id == conversation_id)
        ).scalar_one_or_none()

    @staticmethod
    def lock(db: Session, conversation_id: int) -> Optional[Tuple[int, int, str]]:
        """``FOR UPDATE`` the state row (only that row); returns ``(generation, app_id, session_id)`` read in the
        same statement, or None when the row does not exist (the conversation was deleted: it goes by FK cascade)."""
        row = db.execute(
            select(ChatConversationState.generation, ChatConversationState.app_id, Conversation.session_id)
            .join(Conversation, Conversation.conversation_id == ChatConversationState.conversation_id)
            .where(ChatConversationState.conversation_id == conversation_id)
            .with_for_update(of=ChatConversationState)
        ).one_or_none()
        return (int(row[0]), int(row[1]), str(row[2])) if row is not None else None

    @staticmethod
    def get_binding(db: Session, conversation_id: int) -> Optional[Tuple[int, str]]:
        """``(generation, session_id)`` read in ONE statement (a reset changes both in one transaction), so a
        turn is bound to exactly one thread; None when the state row does not exist."""
        row = db.execute(
            select(ChatConversationState.generation, Conversation.session_id)
            .join(Conversation, Conversation.conversation_id == ChatConversationState.conversation_id)
            .where(ChatConversationState.conversation_id == conversation_id)
        ).one_or_none()
        return (int(row[0]), str(row[1])) if row is not None else None

    @staticmethod
    def rotate_session(db: Session, conversation_id: int, new_session_id: str) -> None:
        """Point the conversation at a fresh (empty) thread and zero its counters (call under ``lock``)."""
        db.execute(
            update(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .values(session_id=new_session_id, message_count=0, last_message=None, updated_at=datetime.utcnow())
        )

    @staticmethod
    def bump_generation(db: Session, conversation_id: int) -> None:
        """Increment the generation (call under ``lock``); invalidates the in-flight turns of the conversation.

        Also clears the busy marker: a reset always wins, and the stale turn's release then matches nothing.
        """
        db.execute(
            update(ChatConversationState)
            .where(ChatConversationState.conversation_id == conversation_id)
            .values(
                generation=ChatConversationState.generation + 1,
                busy_token=None,
                busy_until=None,
                updated_at=datetime.utcnow(),
            )
        )

    @staticmethod
    def claim_busy(db: Session, conversation_id: int, token: uuid.UUID, ttl_seconds: int) -> bool:
        """Compare-and-set the "turn in flight" marker; False when an unexpired marker (or no row) exists.

        Uses the database clock (``clock_timestamp``): replicas with skewed clocks agree, and the value is
        correct inside a long transaction. The caller commits.
        """
        result = db.execute(
            update(ChatConversationState)
            .where(
                ChatConversationState.conversation_id == conversation_id,
                or_(
                    ChatConversationState.busy_until.is_(None),
                    ChatConversationState.busy_until < func.clock_timestamp(),
                ),
            )
            .values(busy_token=token, busy_until=func.clock_timestamp() + timedelta(seconds=ttl_seconds))
        )
        return result.rowcount == 1

    @staticmethod
    def renew_busy(db: Session, conversation_id: int, token: uuid.UUID, ttl_seconds: int) -> bool:
        """Push this claim's expiry to ``now + ttl`` (database clock); False when it is no longer this claim's.

        Called right before the model runs so the time spent preparing the turn (files, indexing, MCP loading) does
        not eat the TTL. The caller commits.
        """
        result = db.execute(
            update(ChatConversationState)
            .where(
                ChatConversationState.conversation_id == conversation_id,
                ChatConversationState.busy_token == token,
            )
            .values(busy_until=func.clock_timestamp() + timedelta(seconds=ttl_seconds))
        )
        return result.rowcount == 1

    @staticmethod
    def release_busy(db: Session, conversation_id: int, token: uuid.UUID) -> None:
        """Clear the marker only if it is still this claim's (a no-op otherwise). The caller commits."""
        db.execute(
            update(ChatConversationState)
            .where(
                ChatConversationState.conversation_id == conversation_id,
                ChatConversationState.busy_token == token,
            )
            .values(busy_token=None, busy_until=None)
        )

    @staticmethod
    def exists(db: Session, conversation_id: int) -> bool:
        return db.execute(
            select(ChatConversationState.conversation_id).where(ChatConversationState.conversation_id == conversation_id)
        ).first() is not None

    @staticmethod
    def ensure(db: Session, conversation_id: int, app_id: int, selection: Dict[str, Any]) -> None:
        """Create the state row if it does not exist (``ON CONFLICT DO NOTHING``)."""
        stmt = (
            pg_insert(ChatConversationState.__table__)
            .values(conversation_id=conversation_id, app_id=app_id, selection=selection, updated_at=datetime.utcnow())
            .on_conflict_do_nothing(index_elements=["conversation_id"])
        )
        db.execute(stmt)

    @staticmethod
    def upsert(db: Session, conversation_id: int, app_id: int, selection: Dict[str, Any]) -> None:
        """Write the conversation's selection (``updated_at`` set explicitly)."""
        now = datetime.utcnow()
        stmt = pg_insert(ChatConversationState.__table__).values(
            conversation_id=conversation_id, app_id=app_id, selection=selection, updated_at=now
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["conversation_id"],
                set_={"selection": stmt.excluded.selection, "app_id": stmt.excluded.app_id, "updated_at": now},
            )
        )


class ChatOptionsRepository:
    """Read queries behind the options payload and the selection resolver (fixed query count)."""

    @staticmethod
    def app_is_frozen(db: Session, app_id: int) -> Optional[bool]:
        """``App.is_frozen`` (tier downgrade), or None when the App does not exist."""
        return db.execute(select(App.is_frozen).where(App.app_id == app_id)).scalar_one_or_none()

    @staticmethod
    def app_default_embedding_service(db: Session, app_id: int) -> Optional[EmbeddingService]:
        """The App's default embedding service (Chat attachment indexing), or None. One query."""
        return db.execute(
            select(EmbeddingService)
            .join(App, App.default_embedding_service_id == EmbeddingService.service_id)
            .where(App.app_id == app_id)
        ).scalar_one_or_none()

    @staticmethod
    def app_chat_sandbox(db: Session, app_id: int) -> Tuple[bool, Optional[int], Optional[SandboxService]]:
        """``(Chat switch, default_sandbox_service_id, that service or None)``. One query.

        The id is returned next to the row so "an App default is set" is never confused with "no default": a set id
        whose row cannot be read must not be treated as the system default.
        """
        row = db.execute(
            select(App.chat_code_interpreter_enabled, App.default_sandbox_service_id, SandboxService)
            .select_from(App)
            .outerjoin(SandboxService, App.default_sandbox_service_id == SandboxService.service_id)
            .where(App.app_id == app_id)
        ).one_or_none()
        if row is None:
            return False, None, None
        return bool(row[0]), row[1], row[2]

    @staticmethod
    def sandbox_service_by_id(db: Session, service_id: int) -> Optional[SandboxService]:
        """A sandbox service by id (the turn re-reads the one it resolved, never a stale ORM object), or None."""
        return db.get(SandboxService, service_id)

    @staticmethod
    def _ai_service_scope(app_id: int):
        return or_(AIService.app_id == app_id, AIService.app_id.is_(None))

    @staticmethod
    def ai_services(db: Session, app_id: int) -> List[AIService]:
        """AI services of the App then system services, each by ``service_id`` (stable order). One query."""
        return list(
            db.execute(
                select(AIService)
                .where(ChatOptionsRepository._ai_service_scope(app_id))
                .order_by(AIService.app_id.is_(None), AIService.service_id)
            ).scalars()
        )

    @staticmethod
    def ai_service(db: Session, app_id: int, service_id: int) -> Optional[AIService]:
        """AI service ``service_id`` if it belongs to the App or is a system service."""
        return db.execute(
            select(AIService).where(
                AIService.service_id == service_id, ChatOptionsRepository._ai_service_scope(app_id)
            )
        ).scalar_one_or_none()

    @staticmethod
    def silos(db: Session, app_id: int, silo_ids: Optional[Iterable[int]] = None) -> List[Silo]:
        """User-selectable silos of the App with their embedding service (joined), by ``silo_id``.

        Excludes frozen silos (tier downgrade), silos without an embedding service (cannot be searched) and the
        temporary silos of chat attachments. One query.
        """
        stmt = (
            select(Silo)
            .options(joinedload(Silo.embedding_service))
            .where(
                Silo.app_id == app_id,
                Silo.is_frozen.is_(False),
                Silo.embedding_service_id.is_not(None),
                SiloRepository.visible_clause(),  # the one definition of "temp"
            )
            .order_by(Silo.silo_id)
        )
        if silo_ids is not None:
            ids = list(silo_ids)
            if not ids:
                return []
            stmt = stmt.where(Silo.silo_id.in_(ids))
        return list(db.execute(stmt).scalars().unique())

    @staticmethod
    def silo_sources(db: Session, app_id: int, silo_ids: Sequence[int]) -> Dict[int, Tuple[str, Optional[str]]]:
        """``silo_id -> (source_type, source_name)`` (repository / domain / sharepoint). Three queries.

        Silos without any source are absent from the result (the caller labels them ``silo``).
        """
        ids = list(silo_ids)
        if not ids:
            return {}
        out: Dict[int, Tuple[str, Optional[str]]] = {}
        for source_type, model in (("sharepoint", SharePointSource), ("domain", Domain), ("repository", Repository)):
            rows = db.execute(
                select(model.silo_id, model.name).where(model.app_id == app_id, model.silo_id.in_(ids))
            ).all()
            for silo_id, name in rows:
                out[silo_id] = (source_type, name)
        return out

    @staticmethod
    def selectable_skills(db: Session, app_id: int) -> List[Skill]:
        """Skills the App may pick (own + enabled non-colliding system skills); light columns. One query."""
        return SkillRepository.get_selectable_for_app(db, app_id, exclude_frozen=True)

    @staticmethod
    def selectable_skills_by_ids(db: Session, app_id: int, skill_ids: Sequence[int]) -> List[Skill]:
        """Fully loaded skills among ``skill_ids`` that the App may pick (same rule as ``selectable_skills``),
        by ``skill_id``. One query whose cost follows the selection."""
        return SkillRepository.get_selectable_by_ids(db, app_id, list(skill_ids))

    @staticmethod
    def mcp_configs(db: Session, app_id: int, config_ids: Optional[Iterable[int]] = None) -> List[MCPConfig]:
        """MCP configs of the App by ``config_id`` (one query), optionally restricted to ``config_ids``."""
        stmt = select(MCPConfig).where(MCPConfig.app_id == app_id).order_by(MCPConfig.config_id)
        if config_ids is not None:
            ids = list(config_ids)
            if not ids:
                return []
            stmt = stmt.where(MCPConfig.config_id.in_(ids))
        return list(db.execute(stmt).scalars())

    @staticmethod
    def mcp_config_names(db: Session, app_id: int) -> List[Tuple[int, str]]:
        """``(config_id, name)`` of the App's MCP configs; never loads the (secret-bearing) ``config`` column."""
        return [
            (cid, name)
            for cid, name in db.execute(
                select(MCPConfig.config_id, MCPConfig.name)
                .where(MCPConfig.app_id == app_id)
                .order_by(MCPConfig.config_id)
            ).all()
        ]

    # --- existence checks used to flag deleted resources of past turns (one query per type) -----------

    @staticmethod
    def existing_ai_service_ids(db: Session, app_id: int, ids: Sequence[int]) -> Set[int]:
        if not ids:
            return set()
        return set(
            db.execute(
                select(AIService.service_id).where(
                    AIService.service_id.in_(list(ids)), ChatOptionsRepository._ai_service_scope(app_id)
                )
            ).scalars()
        )

    @staticmethod
    def existing_silo_ids(db: Session, app_id: int, ids: Sequence[int]) -> Set[int]:
        if not ids:
            return set()
        return set(
            db.execute(select(Silo.silo_id).where(Silo.silo_id.in_(list(ids)), Silo.app_id == app_id)).scalars()
        )

    @staticmethod
    def existing_skill_ids(db: Session, app_id: int, ids: Sequence[int]) -> Set[int]:
        if not ids:
            return set()
        return set(
            db.execute(
                select(Skill.skill_id).where(
                    Skill.skill_id.in_(list(ids)), or_(Skill.app_id == app_id, Skill.app_id.is_(None))
                )
            ).scalars()
        )

    @staticmethod
    def existing_mcp_config_ids(db: Session, app_id: int, ids: Sequence[int]) -> Set[int]:
        if not ids:
            return set()
        return set(
            db.execute(
                select(MCPConfig.config_id).where(MCPConfig.config_id.in_(list(ids)), MCPConfig.app_id == app_id)
            ).scalars()
        )
