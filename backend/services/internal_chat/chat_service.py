"""Business logic of the flexible per-App Chat.

``InternalChatService`` sits between the router and the execution stack. It owns:

* the hidden per-App internal chat agent (get-or-create, never mutated);
* validating the client's selection BEFORE anything is created (no conversation / message / metrics
  event / turn row on an invalid selection);
* the Chat conversations of the calling user (always loaded through the App's internal agent);
* the per-user defaults and per-conversation state, and the per-turn snapshot (``conversation_turn``).

Isolation rules enforced here: ``app_id`` of every row written comes from the conversation's internal
agent, never from request input; defaults are written per ``(user_id, app_id)``; every lookup that
fails for any reason raises the same ``ChatResourceNotFoundError``.

``db`` MUST be the same Session handed to ``AgentExecutionService`` / ``AgentStreamingService``: the
completion hook runs inside a SAVEPOINT of that session and relies on it to commit.
"""
import asyncio
import copy
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from models.conversation import Conversation, ConversationSource
from models.hitl_approval import ApprovalChannel
from repositories.internal_chat_repository import (
    ChatConversationStateRepository,
    ChatOptionsRepository,
    ChatUserDefaultRepository,
    ConversationTurnRepository,
    InternalChatAgentRepository,
    set_local_timeouts,
)
from schemas.conversation_schemas import ConversationUpdate
from schemas.internal_chat_schemas import (
    ChatAIServiceOption,
    ChatAttachmentIndexing,
    ChatCodeInterpreter,
    ChatMcpConfigOption,
    ChatOptionsResponse,
    ChatSelection,
    ChatSelectionWarning,
    ChatSiloOption,
    ChatSkillOption,
    ChatTurnInfo,
)
from services.agent_execution_context import TurnCompleted, TurnCompletedHook
from services.chat_attachment_service import ATTACHMENT_INDEXING_TIMEOUT_SECONDS, ChatAttachmentService
from services.conversation_service import ConversationService
from services.internal_chat.errors import ChatConversationBusyError, ChatResourceNotFoundError
from services.internal_chat.resolved_config import ResolvedChatConfig
from services.internal_chat.selection_resolver import ChatSelectionResolver
from services.internal_chat.system_prompt import get_internal_chat_system_prompt
from services.internal_chat.turn_info import build_turn_info, match_turns_to_messages, snapshot_ids
from services.service_lifecycle_service import ServiceLifecycleService
from tools.stream_guard import AGENT_RUN_TIMEOUT_SECONDS
from utils.logger import get_logger
from utils.service_lifecycle import is_retired

logger = get_logger(__name__)

SANDBOX_DESTROY_TIMEOUT_S = 10.0  # bound of the off-loop sandbox destroy on conversation delete / reset
_destroy_pool = None


def _destroy_executor():
    """Small dedicated executor for sandbox destroys (never the default one, which tool threads can saturate)."""
    global _destroy_pool
    if _destroy_pool is None:
        from concurrent.futures import ThreadPoolExecutor

        _destroy_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sandbox_destroy")
    return _destroy_pool


CALLER_TYPE_INTERNAL_CHAT = ApprovalChannel.INTERNAL_CHAT.name  # "INTERNAL_CHAT": agent_execution_caller_type label

# Only these keys of the caller's context reach a Chat turn (allow-list). Anything else (api_key, billing_user_id,
# scheduled_task_id, hitl_conversation_id, source, ...) would change access, billing or channel rules.
_ALLOWED_CONTEXT_KEYS = ("user_id", "email", "oauth", "token")

DOWNLOAD_LINK_TTL_SECONDS = 300  # Chat download links are short-lived

# Bounds of every transaction that takes the conversation-state lock (hook, reset): the code runs on a
# synchronous session, so an unbounded lock wait would also freeze the event loop.
HOOK_LOCK_TIMEOUT_MS = 3000
HOOK_STATEMENT_TIMEOUT_MS = 8000
# A turn in flight owns its conversation for at most the agent run timeout plus a margin; a crashed turn
# blocks only that conversation, until the marker expires (database clock).
BUSY_MARKER_TTL_SECONDS = AGENT_RUN_TIMEOUT_SECONDS + 60
_LOCK_NOT_AVAILABLE = "55P03"  # PostgreSQL SQLSTATE lock_not_available (the local lock_timeout expired)


@dataclass
class TurnClaim:
    """This turn's claim on its conversation (``busy_token``); every exit releases exactly this one."""

    conversation_id: int
    token: uuid.UUID
    released: bool = False  # True only once the release was COMMITTED (a failed attempt can be retried)


@dataclass(frozen=True)
class PreparedChatTurn:
    """Everything the router passes to the execution / streaming service for one turn."""

    agent_id: int
    conversation_id: int  # plain value: ``conversation`` (ORM) expires on every commit
    conversation: Conversation
    turn_config: ResolvedChatConfig
    on_turn_completed: TurnCompletedHook
    user_context: Dict[str, Any]
    # Selected resources skipped for this turn (an unusable MCP config): the turn runs without them.
    warnings: Tuple[ChatSelectionWarning, ...] = ()
    # True when ``prepare_turn`` created the conversation (no ``conversation_id`` was given).
    created: bool = False
    # The busy-marker claim of this turn (None only for hand-built test doubles).
    claim: Optional[TurnClaim] = None


@dataclass(frozen=True)
class _TurnGuard:
    """What ``prepare_turn`` captured for the completion hook (plain values; nothing ORM)."""

    conversation_id: int
    agent_id: int
    session_id: str
    generation: int  # chat_conversation_state.generation when the turn started
    selection: Dict[str, Any]  # what the user asked for (persisted as state / default)
    warnings: Tuple[ChatSelectionWarning, ...] = ()
    busy_token: Optional[uuid.UUID] = None  # released in the hook's own transaction on success


@dataclass(frozen=True)
class AttachmentScope:
    """Server-side scope of one conversation's attachments (nothing here comes from the client)."""

    agent_id: int
    conversation_id: int
    session_id: str
    context: Dict[str, Any]


@dataclass
class ChatConversationDetail:
    """History of a Chat conversation with the per-message turn snapshot."""

    conversation: Conversation
    messages: List[Dict[str, Any]]  # history dicts; assistant messages carry ``turn`` (ChatTurnInfo | None)
    current_selection: Optional[ChatSelection]
    warnings: List[ChatSelectionWarning] = field(default_factory=list)
    pending_approval: Optional[Dict[str, Any]] = None


class InternalChatService:
    """Chat use cases of one authenticated user. Cheap to build: one instance per request."""

    def __init__(self, db: Session, user_context: Dict[str, Any]):
        self.db = db
        self._user_context = dict(user_context or {})
        raw_user_id = self._user_context.get("user_id")
        if isinstance(raw_user_id, str) and raw_user_id.isdigit():
            raw_user_id = int(raw_user_id)
        # bool is an int subclass: True must not become user 1.
        self._user_id: Optional[int] = (
            raw_user_id if isinstance(raw_user_id, int) and not isinstance(raw_user_id, bool) else None
        )

    # ------------------------------------------------------------------ helpers

    def _access_context(self) -> Dict[str, Any]:
        """Minimal context for ``ConversationService`` ownership checks (the user's id and nothing else)."""
        return {"user_id": self._user_id}

    def build_turn_user_context(self, app_id: int) -> Dict[str, Any]:
        """``user_context`` for the execution stack: ``app_id`` of the internal agent and the INTERNAL_CHAT caller."""
        context = {k: self._user_context[k] for k in _ALLOWED_CONTEXT_KEYS if k in self._user_context}
        context["app_id"] = app_id
        context["caller_type_override"] = CALLER_TYPE_INTERNAL_CHAT
        return context

    def _guard_new_activity(self, app_id: int) -> None:
        """Entry check of every operation that offers choices or starts a turn (options, create, prepare_turn).

        A user is required, and a frozen App (tier downgrade) rejects the Chat with the same 403 a frozen agent
        gives the playground. Existing conversations stay listable/readable/renamable/deletable, as the
        playground allows for a frozen agent (it only blocks execution). Frozen silos and skills are not
        selectable (filtered in the queries); AI services and MCP configs have no ``is_frozen``.
        """
        self._require_user()
        frozen = ChatOptionsRepository.app_is_frozen(self.db, app_id)
        if frozen is None:
            raise ChatResourceNotFoundError()
        if frozen:
            raise HTTPException(
                status_code=403,
                detail="This app is frozen because your subscription tier has been downgraded. "
                       "Please upgrade your plan or delete other resources to unfreeze it.",
            )

    def _require_user(self) -> None:
        """Chat conversations belong to a user; anything else is indistinguishable from "not found"."""
        if self._user_id is None:
            raise ChatResourceNotFoundError()

    def _internal_agent_id_or_404(self, app_id: int) -> int:
        agent_id = InternalChatAgentRepository.get_id(self.db, app_id)
        if agent_id is None:
            raise ChatResourceNotFoundError()
        return agent_id

    def _load_conversation(self, app_id: int, conversation_id: int) -> Conversation:
        """The caller's Chat conversation of this App, or ``ChatResourceNotFoundError`` (whatever the reason)."""
        self._require_user()
        agent_id = self._internal_agent_id_or_404(app_id)
        conversation = ConversationService.get_conversation(
            self.db, conversation_id, self._access_context(), agent_id=agent_id, include_internal_chat=True
        )
        if conversation is None or conversation.source != ConversationSource.INTERNAL_CHAT:
            raise ChatResourceNotFoundError()
        return conversation

    def _default_selection(
        self, app_id: int, services: Optional[List[Any]] = None
    ) -> Tuple[Optional[ChatSelection], List[ChatSelectionWarning]]:
        """The user's stored default (sanitized) or the App default (from ``services`` if already loaded)."""
        warnings: List[ChatSelectionWarning] = []
        selection: Optional[ChatSelection] = None
        if self._user_id is not None:
            stored = ChatUserDefaultRepository.get(self.db, self._user_id, app_id)
            selection, warnings = ChatSelectionResolver.sanitize(self.db, app_id, stored)
        if selection is None:
            selection = ChatSelectionResolver.app_default(self.db, app_id, services)
        return selection, warnings

    # ------------------------------------------------------------------ options

    def get_options(self, app_id: int) -> ChatOptionsResponse:
        """Everything the Chat UI can offer, with the user's sanitized default. A fixed number of queries.

        Raises:
            HTTPException: 403 when the App is frozen.
        """
        self._guard_new_activity(app_id)
        warning_days = ServiceLifecycleService.warning_days(self.db)
        all_ai_services = ChatOptionsRepository.ai_services(self.db, app_id)
        ai_services = [
            ChatAIServiceOption(
                service_id=s.service_id,
                name=s.name,
                provider=getattr(s.provider, "value", s.provider),
                model_name=s.description,
                is_system=s.app_id is None,
                **ServiceLifecycleService.option_fields(s, warning_days),
            )
            for s in all_ai_services
            if not is_retired(s)
        ]

        silo_rows = ChatOptionsRepository.silos(self.db, app_id)
        sources = ChatOptionsRepository.silo_sources(self.db, app_id, [s.silo_id for s in silo_rows])
        silos = []
        for silo in silo_rows:
            source_type, source_name = sources.get(silo.silo_id, ("silo", None))
            silos.append(
                ChatSiloOption(
                    silo_id=silo.silo_id,
                    name=silo.name,
                    source_type=source_type,
                    source_name=source_name,
                    disabled_reason="embedding_service_retired" if is_retired(silo.embedding_service) else None,
                )
            )

        skills = [
            ChatSkillOption(skill_id=s.skill_id, name=s.name, description=s.description, is_system=s.app_id is None)
            for s in ChatOptionsRepository.selectable_skills(self.db, app_id)
            if s.is_enabled
        ]
        mcp_configs = [
            ChatMcpConfigOption(config_id=cid, name=name)
            for cid, name in ChatOptionsRepository.mcp_config_names(self.db, app_id)
        ]

        default, warnings = self._default_selection(app_id, all_ai_services)
        _, indexing = self._attachment_indexing(app_id)
        code_interpreter = self._code_interpreter_state(app_id)
        return ChatOptionsResponse(
            ai_services=ai_services,
            silos=silos,
            skills=skills,
            mcp_configs=mcp_configs,
            default_selection=default,
            default_warnings=warnings,
            has_usable_model=bool(ai_services),
            attachment_indexing=indexing,
            code_interpreter=code_interpreter,
        )

    def _attachment_indexing(self, app_id: int) -> Tuple[Optional[int], ChatAttachmentIndexing]:
        """``(embedding service id to index with or None, state for the UI)`` from the App's default.

        Enabled while the default exists and is active or deprecated; a retired default is never used.
        """
        service = ChatOptionsRepository.app_default_embedding_service(self.db, app_id)
        if service is None:
            return None, ChatAttachmentIndexing(enabled=False, reason="no_default_embedding_service")
        if is_retired(service):
            return None, ChatAttachmentIndexing(enabled=False, reason="embedding_service_retired")
        return service.service_id, ChatAttachmentIndexing(enabled=True)

    def _code_interpreter_state(self, app_id: int) -> ChatCodeInterpreter:
        """State for the UI, from the same single decision the turn uses (``code_interpreter_service``)."""
        service, reason = ChatSelectionResolver.code_interpreter_service(self.db, app_id)
        return ChatCodeInterpreter(enabled=service is not None, reason=reason)

    # ------------------------------------------------------------------ conversations

    def list_conversations(self, app_id: int, limit: int = 50, offset: int = 0) -> Tuple[List[Conversation], int]:
        """The caller's Chat conversations. Never creates the internal agent (a GET has no side effects)."""
        agent_id = InternalChatAgentRepository.get_id(self.db, app_id)
        if agent_id is None or self._user_id is None:
            return [], 0
        return ConversationService.list_conversations(
            self.db, agent_id, self._access_context(), limit=limit, offset=offset, include_internal_chat=True
        )

    def _create_conversation_row(
        self, app_id: int, title: Optional[str], selection_dict: Dict[str, Any]
    ) -> Conversation:
        """Get-or-create the internal agent, then create the conversation and its state row in ONE transaction."""
        agent_id = InternalChatAgentRepository.get_or_create(self.db, app_id, get_internal_chat_system_prompt())
        try:
            conversation = ConversationService.create_conversation(
                self.db,
                agent_id,
                self._access_context(),
                title=title,
                source=ConversationSource.INTERNAL_CHAT,
                auto_title=False,
                commit=False,
            )
            # The state row serializes turn allocation: it exists from the conversation's creation.
            ChatConversationStateRepository.ensure(self.db, conversation.conversation_id, app_id, selection_dict)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return conversation

    def create_conversation(
        self, app_id: int, selection: Optional[ChatSelection] = None, title: Optional[str] = None
    ) -> Tuple[Conversation, Optional[ChatSelection]]:
        """Create a Chat conversation with an initial selection.

        A provided ``selection`` is validated first (nothing is created when it is invalid) and stored as the
        user asked for it (even if one MCP config is unusable); otherwise the user's sanitized default (or the
        App default) is used. Returns the conversation and its initial selection (None when the App has no
        usable model yet).

        Raises:
            ChatResourceNotFoundError / ServiceRetiredError: invalid ``selection``.
            HTTPException: 403 when the App is frozen.
        """
        self._guard_new_activity(app_id)
        if selection is not None:
            initial: Optional[ChatSelection] = ChatSelectionResolver.resolve_full(self.db, app_id, selection).requested
        else:
            initial, _ = self._default_selection(app_id)
        conversation = self._create_conversation_row(app_id, title, initial.model_dump() if initial else {})
        return conversation, initial

    async def get_conversation_detail(self, app_id: int, conversation_id: int) -> ChatConversationDetail:
        """History with per-message ``ChatTurnInfo``, the (sanitized) current selection and any pending approval."""
        conversation = self._load_conversation(app_id, conversation_id)
        history_context = {**self._access_context(), "app_id": app_id}
        history = await ConversationService.history_of_conversation(
            conversation, history_context, include_message_ids=True
        )

        turns = ConversationTurnRepository.list_for_conversation(self.db, conversation_id)
        infos: Dict[int, ChatTurnInfo] = {}
        if turns:
            existing_ai = ChatOptionsRepository.existing_ai_service_ids(
                self.db, app_id, sorted({t.ai_service_id for t in turns if t.ai_service_id is not None})
            )
            existing_silos = ChatOptionsRepository.existing_silo_ids(
                self.db, app_id, sorted({t.silo_id for t in turns if t.silo_id is not None})
            )
            existing_skills = ChatOptionsRepository.existing_skill_ids(
                self.db, app_id, sorted({i for t in turns for i in snapshot_ids(t.skills)})
            )
            existing_mcp = ChatOptionsRepository.existing_mcp_config_ids(
                self.db, app_id, sorted({i for t in turns for i in snapshot_ids(t.mcp_configs)})
            )
            infos = {
                id(t): build_turn_info(
                    t,
                    existing_ai_service_ids=existing_ai,
                    existing_silo_ids=existing_silos,
                    existing_skill_ids=existing_skills,
                    existing_mcp_config_ids=existing_mcp,
                )
                for t in turns
            }

        matched = match_turns_to_messages(history, turns)
        messages: List[Dict[str, Any]] = []
        for message, turn in zip(history, matched):
            entry = dict(message)
            entry["turn"] = infos.get(id(turn)) if turn is not None else None
            messages.append(entry)

        stored = ChatConversationStateRepository.get(self.db, conversation_id)
        current, warnings = ChatSelectionResolver.sanitize(self.db, app_id, stored)
        pending = ConversationService.pending_approval_of_conversation(self.db, conversation, self._access_context())
        return ChatConversationDetail(
            conversation=conversation,
            messages=messages,
            current_selection=current,
            warnings=warnings,
            pending_approval=pending,
        )

    def rename_conversation(self, app_id: int, conversation_id: int, title: str) -> Conversation:
        """Rename one of the caller's Chat conversations."""
        self._load_conversation(app_id, conversation_id)
        updated = ConversationService.update_conversation(
            self.db, conversation_id, self._access_context(), ConversationUpdate(title=title), include_internal_chat=True
        )
        if updated is None:
            raise ChatResourceNotFoundError()
        return updated

    @staticmethod
    async def _destroy_sandbox_bounded(agent_id: int, conversation_id: int) -> bool:
        """Destroy the conversation's sandbox on a dedicated small executor, with a time bound; never raises.

        The provider call is blocking: it must neither stall the event loop nor fail the delete / reset, and it must
        not queue behind the default executor (which the synchronous sandbox tools can saturate). On timeout the
        registry entry is dropped WITHOUT calling the provider on the loop. Returns True when the destroy was
        confirmed (or there was nothing to destroy); False when it was not: the caller then keeps the persisted
        sandbox state so the DB reaper can still find and destroy the remote sandbox.
        """
        from services.sandbox_session_service import SandboxSessionService, sandbox_session_service

        key = SandboxSessionService.session_key(agent_id, conversation_id)
        loop = asyncio.get_running_loop()
        try:
            return bool(await asyncio.wait_for(
                loop.run_in_executor(_destroy_executor(), sandbox_session_service.destroy_confirmed, key),
                SANDBOX_DESTROY_TIMEOUT_S,
            ))
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001
            sandbox_session_service.evict(key)  # registry only: no provider call on the loop
            logger.warning("Chat: sandbox destroy did not finish (key=%s, %s)", key, type(exc).__name__)
            return False

    async def delete_conversation(self, app_id: int, conversation_id: int) -> None:
        """Delete one of the caller's Chat conversations.

        Order (Chat only; ``ConversationService.delete_conversation`` keeps its own order for other kinds):
        temp media / sandbox first (best effort), then the conversation row is deleted and COMMITTED (the state
        row and turns go by FK cascade), and only then is the LangGraph thread deleted. A turn whose hook runs
        after the commit finds no state row and drops its own thread; whatever it wrote before is removed by the
        thread delete that follows. Thread-delete failures are logged (best effort): the row is already gone.
        """
        conversation = self._load_conversation(app_id, conversation_id)
        agent_id, session_id = conversation.agent_id, conversation.session_id
        self._release_db_connection()
        await self._destroy_sandbox_bounded(agent_id, conversation_id)  # the row is deleted next: nothing to keep
        ConversationService.release_conversation_resources(self.db, conversation)
        try:
            set_local_timeouts(self.db, HOOK_LOCK_TIMEOUT_MS, HOOK_STATEMENT_TIMEOUT_MS)
            self.db.delete(conversation)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        # Attachments (per-user session folder + ``conversations/{id}/`` working dir); best effort, row already gone.
        ChatAttachmentService.delete_storage(agent_id, self._attachment_context(app_id), conversation_id)
        await ConversationService.delete_thread_history(agent_id, session_id)

    async def reset_conversation(self, app_id: int, conversation_id: int) -> None:
        """Forget the history of a conversation: thread, turn snapshots, counters, attachments, temp silo.

        The selection is kept. The conversation gets a NEW ``session_id`` (same ``conv_{agent_id}_{uuid}`` format)
        together with a ``generation`` bump:

        1. ONE transaction, with no ``await`` between the lock and the commit (a sync ``UPDATE`` of the same
           Conversation row elsewhere in the worker would otherwise freeze the event loop on a lock this
           coroutine can only release by awaiting): bounded timeouts, ``FOR UPDATE`` on the state row, bump
           generation, rotate ``session_id``, delete the turn rows, zero the counters, COMMIT. Any failure or
           cancellation rolls back.
        2. After the commit the old thread is unreferenced: delete it (best effort). A failure is logged (ids
           only) and does not fail the reset; the user-visible state is already correct and a turn still bound to
           the old thread drops it itself when it completes.
        3. Best effort: ONLY the attachments that existed before step 1 (a snapshot of their ids taken before the
           locked transaction), then temp media / sandbox of the old session. A file the user uploads right after
           the reset (new session) is never touched.

        Known limit: a stale turn (started before the reset) has already run the shared
        ``increment_message_count``, so right after the reset ``message_count`` / ``last_message`` may still show
        its answer. There is no race-free marker in the schema to tell it apart from the counters of a newer turn.

        Raises:
            ChatResourceNotFoundError: not the caller's conversation (or deleted while resetting).
        """
        conversation = self._load_conversation(app_id, conversation_id)
        agent_id = conversation.agent_id
        # Snapshot BEFORE the locked transaction (it may await; the transaction below must not): the cleanup
        # after the commit removes exactly these ids, so a file uploaded after the commit survives.
        attachment_context = self._attachment_context(app_id)
        self._release_db_connection()
        stale_file_ids = await self._attached_file_ids(agent_id, attachment_context, conversation_id)
        try:
            set_local_timeouts(self.db, HOOK_LOCK_TIMEOUT_MS, HOOK_STATEMENT_TIMEOUT_MS)
            locked = ChatConversationStateRepository.lock(self.db, conversation_id)
            if locked is None:
                raise ChatResourceNotFoundError()
            _, _, old_session_id = locked
            ChatConversationStateRepository.bump_generation(self.db, conversation_id)
            ChatConversationStateRepository.rotate_session(
                self.db, conversation_id, f"conv_{agent_id}_{uuid.uuid4()}"
            )
            ConversationTurnRepository.delete_for_conversation(self.db, conversation_id)
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

        try:
            await ConversationService.delete_thread_history(agent_id, old_session_id)
        except Exception:
            logger.error(
                "Chat reset: could not delete the old thread (conversation_id=%s agent_id=%s thread=%s)",
                conversation_id, agent_id, old_session_id,
            )

        await ChatAttachmentService.remove_many(stale_file_ids, agent_id, attachment_context, conversation_id)
        conversation = self.db.get(Conversation, conversation_id)
        if conversation is not None:
            self._release_db_connection()
            confirmed = await self._destroy_sandbox_bounded(agent_id, conversation_id)
            ConversationService.release_conversation_resources(
                self.db, conversation, session_id=old_session_id, clear_sandbox_state=confirmed
            )
            self.db.commit()

    # ------------------------------------------------------------------ attachments

    def _attachment_context(self, app_id: int) -> Dict[str, Any]:
        """Scope of the stored attachments (file session key = agent + user + App + conversation)."""
        return {"user_id": self._user_id, "oauth": True, "app_id": app_id}

    @staticmethod
    async def _attached_file_ids(agent_id: int, context: Dict[str, Any], conversation_id: int) -> List[str]:
        """Ids of the files currently attached to the conversation (best effort: a failure means none)."""
        try:
            return await ChatAttachmentService.list_file_ids(agent_id, context, conversation_id)
        except Exception:
            logger.error("Chat: could not list attachments (conversation_id=%s agent_id=%s)", conversation_id, agent_id)
            return []

    def _attachment_scope(self, app_id: int, conversation_id: int) -> AttachmentScope:
        """Validate the conversation and read its CURRENT session id from the database (a reset rotates it)."""
        conversation = self._load_conversation(app_id, conversation_id)
        binding = ChatConversationStateRepository.get_binding(self.db, conversation_id)
        if binding is None:
            raise ChatResourceNotFoundError()
        return AttachmentScope(
            agent_id=conversation.agent_id,
            conversation_id=conversation_id,
            session_id=binding[1],
            context=self._attachment_context(app_id),
        )

    async def upload_attachment(self, app_id: int, conversation_id: int, file: UploadFile) -> Dict[str, Any]:
        """Attach ``file`` to the caller's conversation (stored per conversation, indexed into its temp silo)."""
        self._guard_new_activity(app_id)  # a frozen App takes no new chat activity (list/delete/download stay open)
        scope = self._attachment_scope(app_id, conversation_id)
        embedding_service_id, _ = self._attachment_indexing(app_id)
        self._release_db_connection()  # file processing + indexing are slow: hold no pooled connection meanwhile
        return await ChatAttachmentService.upload(
            self.db,
            file,
            agent_id=scope.agent_id,
            app_id=app_id,
            user_context=scope.context,
            conversation_id=scope.conversation_id,
            has_memory=True,  # the internal chat agent always keeps memory
            resolve_session_id=lambda: scope.session_id,
            embedding_service_id=embedding_service_id,
            degrade_when_retired=True,
            index_timeout_seconds=ATTACHMENT_INDEXING_TIMEOUT_SECONDS,
        )

    async def list_attachments(self, app_id: int, conversation_id: int) -> Dict[str, Any]:
        scope = self._attachment_scope(app_id, conversation_id)
        return await ChatAttachmentService.list_files(scope.agent_id, scope.context, scope.conversation_id)

    async def remove_attachment(self, app_id: int, conversation_id: int, file_id: str) -> None:
        """Remove one file of this conversation; any id that is not one of its files is "not found"."""
        scope = self._attachment_scope(app_id, conversation_id)
        if not await ChatAttachmentService.remove(file_id, scope.agent_id, scope.context, scope.conversation_id):
            raise ChatResourceNotFoundError()

    async def attachment_download(
        self, app_id: int, conversation_id: int, file_id: str, request_base_url: str
    ) -> Dict[str, str]:
        """Signed download link of one file of this conversation (never searched outside the conversation)."""
        scope = self._attachment_scope(app_id, conversation_id)
        found = await ChatAttachmentService.find(
            file_id, scope.agent_id, scope.context, [str(scope.conversation_id)]
        )
        email = self._user_context.get("email")
        download = (
            ChatAttachmentService.build_expiring_download(found, email, request_base_url, DOWNLOAD_LINK_TTL_SECONDS)
            if found and email
            else None
        )
        if download is None:
            raise ChatResourceNotFoundError()
        return download

    # ------------------------------------------------------------------ defaults

    def get_defaults(self, app_id: int) -> Optional[ChatSelection]:
        """The user's sanitized default selection, else the App default (None when no usable model)."""
        self._guard_new_activity(app_id)
        selection, _ = self._default_selection(app_id)
        return selection

    def set_defaults(self, app_id: int, selection: ChatSelection) -> ChatSelection:
        """Pin the caller's own default selection (validated like a turn's; only the caller's row is written)."""
        self._guard_new_activity(app_id)
        requested = ChatSelectionResolver.resolve_full(self.db, app_id, selection).requested
        try:
            ChatUserDefaultRepository.upsert(self.db, self._user_id, app_id, requested.model_dump())
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return requested

    # ------------------------------------------------------------------ turns

    def prepare_turn(
        self, app_id: int, selection: ChatSelection, conversation_id: Optional[int] = None
    ) -> PreparedChatTurn:
        """Validate the selection and get the conversation, creating it only when ``conversation_id`` is None.

        Everything is validated before the first write, so an invalid selection leaves no trace. For a new
        conversation the selection is resolved a second time after the creation commit: that commit expires
        the ORM objects of the first resolution, and the turn must run on freshly loaded ones.

        Raises:
            ChatResourceNotFoundError: invalid selection ids / conversation not found / not the caller's.
            ServiceRetiredError: retired AI or embedding service.
            HTTPException: 403 when the App is frozen.
        """
        self._guard_new_activity(app_id)
        conversation: Optional[Conversation] = None
        generation = 0
        bound_session_id: Optional[str] = None
        claim: Optional[TurnClaim] = None
        created_id: Optional[int] = None  # the conversation THIS request created (None when it was given)
        try:
            if conversation_id is not None:
                conversation = self._load_conversation(app_id, conversation_id)
                # One turn at a time per conversation: claim BEFORE any other work, so a second concurrent turn
                # is refused (409) without having touched anything.
                claim = self._claim_conversation(conversation_id)
                # generation and session_id in ONE statement: the turn is bound to exactly one thread. The loaded
                # row is pinned to that value, so the execution stack (which re-reads the conversation through the
                # same session) uses the thread this guard is about.
                binding = ChatConversationStateRepository.get_binding(self.db, conversation_id)
                if binding is None:
                    raise ChatResourceNotFoundError()
                generation, bound_session_id = binding
                set_committed_value(conversation, "session_id", bound_session_id)

            resolved = ChatSelectionResolver.resolve_full(self.db, app_id, selection)
            if conversation is None:
                conversation = self._create_conversation_row(app_id, None, resolved.requested.model_dump())
                created_id = conversation.conversation_id
                # New id, state row created in the same transaction: nobody else can hold it yet.
                claim = self._claim_conversation(created_id)
                resolved = ChatSelectionResolver.resolve_full(self.db, app_id, selection)
            turn_config = resolved.config

            guard = _TurnGuard(
                conversation_id=conversation.conversation_id,
                agent_id=conversation.agent_id,
                session_id=bound_session_id or conversation.session_id,
                generation=generation,
                selection=resolved.requested.model_dump(),
                warnings=resolved.skipped,
                busy_token=claim.token if claim is not None else None,
            )
        except BaseException:
            # Validation / retired service / not found AFTER the claim: give the conversation back (sync).
            self.release_turn(claim)
            if created_id is not None:
                self._drop_created_conversation(created_id)  # nobody has seen it: never leave an empty one behind
            raise

        # Right before the model runs the execution / streaming services call this: the marker then lasts a full
        # run from that moment, however long the preparation took. Never raises.
        turn_config.diagnostics.before_model = lambda: self._renew_or_abort(claim)
        turn_config.diagnostics.renew_marker = lambda: self.renew_turn(claim)
        self._release_db_connection()  # the turn's slow steps (files, indexing, the model) hold no connection

        async def hook(event: TurnCompleted) -> Optional[dict]:
            return await self.on_turn_completed(event, guard)

        logger.info(
            "internal_chat.turn app_id=%s conversation_id=%s user_id=%s ai_service_id=%s silo_id=%s "
            "skill_ids=%s mcp_config_ids=%s",
            app_id,
            guard.conversation_id,
            self._user_id,
            turn_config.ai_service_id,
            turn_config.silo_id,
            list(turn_config.skill_ids),
            list(turn_config.mcp_config_ids),
        )
        return PreparedChatTurn(
            agent_id=guard.agent_id,
            conversation_id=guard.conversation_id,
            conversation=conversation,
            turn_config=turn_config,
            on_turn_completed=hook,
            user_context=self.build_turn_user_context(app_id),
            warnings=resolved.skipped,
            created=conversation_id is None,
            claim=claim,
        )

    def _claim_conversation(self, conversation_id: int) -> TurnClaim:
        """Claim the conversation for one turn (committed at once, so other requests see it).

        Raises:
            ChatConversationBusyError: an unexpired claim exists, or another transaction holds the state row (the
                local lock timeout expired: that is "somebody else is working on it" too, not a server error).
            ChatResourceNotFoundError: the conversation (state row) is gone.
        """
        token = uuid.uuid4()
        try:
            set_local_timeouts(self.db, HOOK_LOCK_TIMEOUT_MS, HOOK_STATEMENT_TIMEOUT_MS)
            claimed = ChatConversationStateRepository.claim_busy(
                self.db, conversation_id, token, BUSY_MARKER_TTL_SECONDS
            )
            if claimed:
                self.db.commit()
                return TurnClaim(conversation_id=conversation_id, token=token)
            exists = ChatConversationStateRepository.exists(self.db, conversation_id)
            self.db.rollback()
        except OperationalError as exc:
            self.db.rollback()
            if getattr(exc.orig, "pgcode", None) == _LOCK_NOT_AVAILABLE:
                raise ChatConversationBusyError() from None
            raise
        except BaseException:
            self.db.rollback()
            raise
        if not exists:
            raise ChatResourceNotFoundError()
        raise ChatConversationBusyError()

    def _release_db_connection(self) -> None:
        """End the session's transaction (objects stay usable) so no pooled connection is held across a slow await.

        ``expire_on_commit`` is off for the commit: the turn's already loaded objects must not become unusable (a
        conversation deleted meanwhile would otherwise fail the finishing steps). Never raises.
        """
        previous_expire = self.db.expire_on_commit
        try:
            self.db.expire_on_commit = False
            self.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chat: could not end the transaction before a slow step (%s)", type(exc).__name__)
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            self.db.expire_on_commit = previous_expire

    def renew_turn(self, claim: Optional[TurnClaim]) -> bool:
        """Push the claim's expiry a full TTL ahead. Synchronous, bounded by the local timeouts, never raises.

        Returns False ONLY when the marker is no longer this turn's (lost: expired and taken over, or reset): the
        caller must abort the turn. If the renewal merely fails, the marker keeps the expiry it had (True).
        """
        if claim is None or claim.released:
            return True
        previous_expire = self.db.expire_on_commit
        still_ours = True
        try:
            set_local_timeouts(self.db, HOOK_LOCK_TIMEOUT_MS, HOOK_STATEMENT_TIMEOUT_MS)
            still_ours = ChatConversationStateRepository.renew_busy(
                self.db, claim.conversation_id, claim.token, BUSY_MARKER_TTL_SECONDS
            )
            # Keep the objects the turn has already loaded as they are: expiring them here would make a conversation
            # deleted while the model runs fail the finishing steps with ``ObjectDeletedError`` (they read it again).
            self.db.expire_on_commit = False
            self.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Chat: could not renew the busy marker of conversation %s (%s)",
                claim.conversation_id, type(exc).__name__,
            )
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            self.db.expire_on_commit = previous_expire
        return still_ours

    def _renew_or_abort(self, claim: Optional[TurnClaim]) -> bool:
        """Renew the marker; abort the turn with CONVERSATION_BUSY when it was lost (someone else may be running)."""
        if not self.renew_turn(claim):
            logger.warning("Chat: the busy marker of conversation %s was lost; aborting the turn",
                           claim.conversation_id if claim is not None else None)
            raise ChatConversationBusyError()
        return True

    def release_turn(self, claim: Optional[TurnClaim]) -> None:
        """Release this turn's claim. Synchronous on purpose (no ``await``: a cancelled task's ``finally`` may be
        re-cancelled at the first await), bounded by the local lock/statement timeouts, idempotent, and it never
        raises, so it cannot mask the original error or cancellation. A claim already taken over (expiry), cleared
        (reset) or deleted with its conversation matches nothing. ``claim.released`` is set only after the commit, so
        a failed attempt can be retried by the safety net of the caller."""
        if claim is None or claim.released:
            return
        try:
            self.db.rollback()  # the failed/cancelled turn may have left an open or aborted transaction
            set_local_timeouts(self.db, HOOK_LOCK_TIMEOUT_MS, HOOK_STATEMENT_TIMEOUT_MS)
            ChatConversationStateRepository.release_busy(self.db, claim.conversation_id, claim.token)
            self.db.commit()
            claim.released = True
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Chat: could not release the busy marker of conversation %s (%s); it expires by itself",
                claim.conversation_id, type(exc).__name__,
            )
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass

    @contextmanager
    def turn_scope(self, prepared: PreparedChatTurn) -> Iterator[None]:
        """The single owner of a prepared turn's claim for the synchronous endpoint: leaving the block, however it
        ends, releases it (a no-op when the completion hook already did)."""
        try:
            yield
        finally:
            self.release_turn(prepared.claim)

    def _drop_created_conversation(self, conversation_id: int) -> None:
        """Delete a conversation this request just created and never used (its turn failed before it started).

        Synchronous and best effort (it never raises): the row only, because nothing was stored yet (no files, no
        thread, no temp silo); the state row goes by FK cascade.
        """
        try:
            self.db.rollback()
            conversation = self.db.get(Conversation, conversation_id)
            if conversation is not None and not conversation.message_count:
                self.db.delete(conversation)
                self.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Chat: could not drop the unused conversation %s (%s)", conversation_id, type(exc).__name__
            )
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass

    async def discard_created_conversation(self, app_id: int, prepared: PreparedChatTurn) -> None:
        """Best effort: delete the conversation ``prepared`` created when its first turn failed before answering.

        Only a conversation created by that very request (``prepared.created``) and still empty (no messages, no
        persisted turn) is removed, through the normal delete path (state rows, storage and thread go too). It never
        raises, so it cannot mask the error the caller is about to re-raise.
        """
        if not prepared.created:
            return
        if prepared.turn_config.diagnostics.step_limit_reached:
            return  # the turn ran out of steps: keep the conversation, its checkpoint, files and sandbox
        conversation_id = prepared.conversation_id
        try:
            self.db.rollback()  # the failed turn may have left the session in an aborted transaction
            conversation = self._load_conversation(app_id, conversation_id)
            if conversation.message_count or ConversationTurnRepository.list_for_conversation(self.db, conversation_id):
                return
            await self.delete_conversation(app_id, conversation_id)
            logger.info("Chat: discarded the empty conversation %s of a failed first turn", conversation_id)
        except Exception:
            logger.warning("Chat: could not discard the empty conversation %s of a failed first turn", conversation_id)

    async def on_turn_completed(self, event: TurnCompleted, guard: _TurnGuard) -> Optional[dict]:
        """Persist the completed turn (``TurnCompletedHook`` body): runs in a SAVEPOINT; never commits.

        Order (short lock window): bound lock/statement waits (``SET LOCAL``, ended by the runner's commit or
        rollback) -> silo source lookup -> ``FOR UPDATE`` on the conversation's state row -> compare
        ``generation`` -> next ``turn_index`` -> insert turn -> update state -> upsert the user's default (last).

        Returns the allow-listed ``ChatTurnInfo`` as a JSON-ready dict (``done.turn``), or None when nothing was
        persisted because the conversation was deleted or reset while the turn ran (INFO log; the turn's thread
        is deleted again (after a reset: the old, rotated-away thread), in the background, on another connection that takes none of this transaction's locks --
        it is never awaited here -- so it cannot deadlock with the state-row lock).

        Raises:
            RuntimeError: the event does not belong to the guarded conversation / App (programming error).
            sqlalchemy.exc.OperationalError: the lock or statement timeout expired (the caller logs it and
                answers without ``turn``).
        """
        config = event.turn_config
        conversation_id = event.conversation_id
        if conversation_id is None or conversation_id != guard.conversation_id:
            raise RuntimeError("completed chat turn does not match the prepared conversation")
        set_local_timeouts(self.db, HOOK_LOCK_TIMEOUT_MS, HOOK_STATEMENT_TIMEOUT_MS)

        silo_source_type: Optional[str] = None
        if config.silo_id is not None:
            source = ChatOptionsRepository.silo_sources(self.db, config.app_id, [config.silo_id]).get(config.silo_id)
            silo_source_type = source[0] if source else "silo"

        locked = ChatConversationStateRepository.lock(self.db, conversation_id)
        if locked is None:
            logger.info("Chat turn completed after its conversation %s was deleted; nothing persisted", conversation_id)
            self._drop_thread(guard)
            return None
        generation, app_id, current_session_id = locked
        if app_id != config.app_id:
            raise RuntimeError("chat turn app does not match the conversation's App")
        if guard.busy_token is not None:
            # Release in the same transaction as the turn row: no window where the turn is stored but the
            # conversation is still "busy". (A reset already cleared it: this matches nothing.)
            ChatConversationStateRepository.release_busy(self.db, conversation_id, guard.busy_token)
        if generation != guard.generation:
            logger.info("Chat turn completed after conversation %s was reset; nothing persisted", conversation_id)
            # A reset rotates the session id, so this turn's thread is no longer referenced by the conversation
            # and dropping it can never touch a thread a newer turn uses. (Equal ids cannot happen; if they
            # ever did, deleting would be unsafe, so it is skipped.)
            if current_session_id != guard.session_id:
                self._drop_thread(guard)
            return None

        execution_event_id: Optional[uuid.UUID] = None
        if event.execution_event_id:
            try:
                execution_event_id = uuid.UUID(str(event.execution_event_id))
            except ValueError:
                execution_event_id = None

        row = ConversationTurnRepository.insert(
            self.db,
            conversation_id=conversation_id,
            app_id=app_id,
            user_id=self._user_id,
            turn_index=ConversationTurnRepository.next_index(self.db, conversation_id),
            assistant_message_id=event.assistant_message_id,
            execution_event_id=execution_event_id,
            ai_service_id=config.ai_service_id,
            ai_service_name=config.ai_service_name,
            ai_model_name=config.ai_service_model,
            silo_id=config.silo_id,
            silo_name=config.silo_name,
            silo_source_type=silo_source_type,
            skills=[{"id": i, "name": n} for i, n in zip(config.skill_ids, config.skill_names)],
            mcp_configs=[{"id": i, "name": n} for i, n in zip(config.mcp_config_ids, config.mcp_config_names)],
        )
        ChatConversationStateRepository.upsert(self.db, conversation_id, app_id, copy.deepcopy(guard.selection))
        if self._user_id is not None:
            ChatUserDefaultRepository.upsert(self.db, self._user_id, app_id, copy.deepcopy(guard.selection))
        # Selected MCP servers whose tools failed to load while the agent was built (reported by tool building).
        unavailable = tuple(
            ChatSelectionWarning(kind="mcp_config", id=i) for i in config.diagnostics.mcp_unavailable_ids
        )
        skipped = config.diagnostics.outputs_skipped
        outputs = (ChatSelectionWarning(kind="sandbox_output", id=skipped),) if skipped > 0 else ()
        return build_turn_info(row, warnings=guard.warnings + unavailable + outputs).model_dump(mode="json")

    @staticmethod
    def _drop_thread(guard: _TurnGuard) -> None:
        """Delete the finished turn's thread again without waiting for it (best effort, background task)."""
        ConversationService.delete_thread_histories_in_background([(guard.agent_id, guard.session_id)])
