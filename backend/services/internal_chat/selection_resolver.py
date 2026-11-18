"""Validation of a chat selection against the App.

``ChatSelectionResolver.resolve`` is the only door through which a client-provided selection becomes a
``ResolvedChatConfig``. Every id is checked against the App (own resources, plus system AI services
and system skills) with a fixed number of queries. Any id that is missing, belongs to another App or
is disabled raises the same ``ChatResourceNotFoundError``; a retired AI/embedding service raises
``ServiceRetiredError`` (only after every id was proven to be visible, so it never leaks across Apps).

Chat suitability of an AI service: ``AIService`` has no "chat capable" flag, so every non-retired
service of the App (or system service) is selectable.
"""
import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import ValidationError
from sqlalchemy.orm import Session

from models.hitl_approval import ApprovalChannel
from repositories.internal_chat_repository import ChatOptionsRepository
from schemas.internal_chat_schemas import ChatSelection, ChatSelectionWarning
from services.internal_chat.errors import ChatResourceNotFoundError
from services.internal_chat.resolved_config import McpConnectionSpec, ResolvedChatConfig
from services.internal_chat.system_prompt import get_internal_chat_system_prompt
from utils.logger import get_logger
from utils.service_lifecycle import (
    SERVICE_KIND_AI,
    SERVICE_KIND_EMBEDDING,
    ensure_service_active,
    is_retired,
    service_call_context,
)

logger = get_logger(__name__)

_CALL_CHANNEL = ApprovalChannel.INTERNAL_CHAT.value


@dataclass(frozen=True)
class ResolvedSelection:
    """Result of ``resolve_full``: the frozen turn config plus what the user actually asked for.

    ``requested`` (deduplicated, validated against the App) is what gets persisted as the conversation's
    selection and the user's default; ``config`` holds only what the turn really uses. They differ when a
    selected MCP config had to be skipped (``skipped`` lists it) -- the user's choice is not forgotten.
    """

    config: ResolvedChatConfig
    requested: ChatSelection
    skipped: Tuple[ChatSelectionWarning, ...]


@dataclass(frozen=True)
class ChatSandboxChoice:
    """Where the Chat's sandbox comes from: an App default service, or (``service=None``) the system default."""

    service: Any = None


@dataclass
class _Loaded:
    """What the App actually has out of a selection (nothing here trusts the request)."""

    ai_service: Any = None
    silo: Any = None
    skills: List[Any] = field(default_factory=list)  # full Skill ORM, ordered by id
    mcp_configs: List[Any] = field(default_factory=list)  # MCPConfig ORM, ordered by id
    missing: List[ChatSelectionWarning] = field(default_factory=list)


def _dedupe(ids: Sequence[int]) -> List[int]:
    return sorted(set(ids))


def _provider_name(service: Any) -> Optional[str]:
    provider = getattr(service, "provider", None)
    return getattr(provider, "value", provider)


class ChatSelectionResolver:
    """Resolve / sanitize chat selections. Stateless; every method takes the session explicitly."""

    @staticmethod
    def _load(db: Session, app_id: int, selection: ChatSelection) -> _Loaded:
        loaded = _Loaded()
        loaded.ai_service = ChatOptionsRepository.ai_service(db, app_id, selection.ai_service_id)
        if loaded.ai_service is None:
            loaded.missing.append(ChatSelectionWarning(kind="ai_service", id=selection.ai_service_id))

        if selection.silo_id is not None:
            silos = ChatOptionsRepository.silos(db, app_id, [selection.silo_id])
            loaded.silo = silos[0] if silos else None
            if loaded.silo is None:
                loaded.missing.append(ChatSelectionWarning(kind="silo", id=selection.silo_id))

        skill_ids = _dedupe(selection.skill_ids)
        if skill_ids:
            found = {s.skill_id: s for s in ChatOptionsRepository.selectable_skills_by_ids(db, app_id, skill_ids)}
            for skill_id in skill_ids:
                skill = found.get(skill_id)
                if skill is None or not skill.is_enabled:
                    loaded.missing.append(ChatSelectionWarning(kind="skill", id=skill_id))
                else:
                    loaded.skills.append(skill)

        mcp_ids = _dedupe(selection.mcp_config_ids)
        if mcp_ids:
            loaded.mcp_configs = ChatOptionsRepository.mcp_configs(db, app_id, mcp_ids)
            found = {c.config_id for c in loaded.mcp_configs}
            loaded.missing.extend(ChatSelectionWarning(kind="mcp_config", id=i) for i in mcp_ids if i not in found)
        return loaded

    @staticmethod
    def _build_mcp_specs(configs: Sequence[Any]) -> Tuple[Tuple[McpConnectionSpec, ...], List[int]]:
        """Connection specs from deep copies, plus the ids of configs skipped as unusable (degradation)."""
        specs: List[McpConnectionSpec] = []
        skipped: List[int] = []
        for config in configs:
            try:
                connections = copy.deepcopy(config.to_connection_dict())
            except ValueError as exc:
                logger.warning("Skipping MCP config %s in the chat: invalid connection config (%s)", config.config_id, exc)
                skipped.append(config.config_id)
                continue
            if not isinstance(connections, dict) or not connections:
                logger.warning("Skipping MCP config %s in the chat: empty or non-object connection config", config.config_id)
                skipped.append(config.config_id)
                continue
            # Token forwarding to URL-based MCP servers (tools.agentTools._connections_from_specs) mirrors the
            # playground by product decision; the Chat adds nothing to it.
            specs.append(
                McpConnectionSpec(
                    config_id=config.config_id,
                    name=config.name,
                    connections=connections,
                    ssl_verify=config.ssl_verify if config.ssl_verify is not None else True,
                )
            )
        return tuple(specs), skipped

    @staticmethod
    def code_interpreter_service(db: Session, app_id: int) -> Tuple[Optional[ChatSandboxChoice], Optional[str]]:
        """The one decision: ``(choice, None)`` when the Chat has a code interpreter, else ``(None, reason)``.

        * switch off: ``disabled_in_app_settings`` (whatever the App default is);
        * App default set: that service (loaded by id, never through the hidden agent's relationships). Retired:
          ``sandbox_service_retired`` and NO fallback to the system default (as for agents); provider not
          registered / not allowed: ``sandbox_provider_unavailable``;
        * no App default: the system default (``SANDBOX_DEFAULT_PROVIDER``, env credentials), exactly like agents
          ("inherit system default"); not registered / not allowed: ``sandbox_provider_unavailable``.

        A database / relationship error never turns into "use the system default": it means no code interpreter
        (class-name-only warning). Never raises: the turn simply runs without code interpreter.
        """
        from tools.sandbox.factory import provider_is_available, system_default_is_available  # lazy: registry

        try:
            enabled, default_id, service = ChatOptionsRepository.app_chat_sandbox(db, app_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chat code interpreter: App sandbox settings unreadable (%s)", type(exc).__name__)
            return None, "sandbox_provider_unavailable"
        if not enabled:
            return None, "disabled_in_app_settings"
        if default_id is None:
            if not system_default_is_available():
                return None, "sandbox_provider_unavailable"
            return ChatSandboxChoice(service=None), None
        if service is None:  # a default is set but its row cannot be read: never the system default
            return None, "sandbox_provider_unavailable"
        if is_retired(service):
            return None, "sandbox_service_retired"
        if not provider_is_available(service):
            return None, "sandbox_provider_unavailable"
        return ChatSandboxChoice(service=service), None

    @staticmethod
    def resolve(db: Session, app_id: int, selection: ChatSelection) -> ResolvedChatConfig:
        """``resolve_full(...).config`` (see there for the errors)."""
        return ChatSelectionResolver.resolve_full(db, app_id, selection).config

    @staticmethod
    def resolve_full(db: Session, app_id: int, selection: ChatSelection) -> ResolvedSelection:
        """Validate ``selection`` against the App and freeze it into a ``ResolvedChatConfig``.

        Raises:
            ChatResourceNotFoundError: any id missing / in another App / disabled (single message).
            ServiceRetiredError: the AI service, or the silo's embedding service, is retired.
        """
        loaded = ChatSelectionResolver._load(db, app_id, selection)
        if loaded.missing:
            raise ChatResourceNotFoundError()

        service, silo = loaded.ai_service, loaded.silo
        with service_call_context(channel=_CALL_CHANNEL, app_id=app_id, resource_type="app_chat"):
            ensure_service_active(service, SERVICE_KIND_AI)
            if silo is not None:
                ensure_service_active(silo.embedding_service, SERVICE_KIND_EMBEDDING)

        mcp_specs, skipped_ids = ChatSelectionResolver._build_mcp_specs(loaded.mcp_configs)
        choice, _ = ChatSelectionResolver.code_interpreter_service(db, app_id)
        sandbox_service = choice.service if choice is not None else None
        config = ResolvedChatConfig(
            app_id=app_id,
            ai_service=service,
            ai_service_id=service.service_id,
            ai_service_name=service.name,
            ai_service_is_system=service.app_id is None,
            ai_service_provider=_provider_name(service),
            ai_service_model=service.description,
            silo=silo,
            silo_id=silo.silo_id if silo is not None else None,
            silo_name=silo.name if silo is not None else None,
            skills=tuple(loaded.skills),
            skill_ids=tuple(s.skill_id for s in loaded.skills),
            skill_names=tuple(s.name for s in loaded.skills),
            mcp_connections=mcp_specs,
            mcp_config_ids=tuple(s.config_id for s in mcp_specs),
            mcp_config_names=tuple(s.name for s in mcp_specs),
            system_prompt=get_internal_chat_system_prompt(),
            skipped_mcp_config_ids=tuple(skipped_ids),
            sandbox_enabled=choice is not None,
            sandbox_service=sandbox_service,
            sandbox_service_id=sandbox_service.service_id if sandbox_service is not None else None,
            sandbox_service_name=sandbox_service.name if sandbox_service is not None else None,
            sandbox_provider=(sandbox_service.provider or "").strip().lower() if sandbox_service is not None else None,
        )
        requested = ChatSelection(
            ai_service_id=service.service_id,
            silo_id=selection.silo_id,
            skill_ids=_dedupe(selection.skill_ids),
            mcp_config_ids=_dedupe(selection.mcp_config_ids),
        )
        return ResolvedSelection(
            config=config,
            requested=requested,
            skipped=tuple(ChatSelectionWarning(kind="mcp_config", id=i) for i in skipped_ids),
        )

    @staticmethod
    def sanitize(
        db: Session, app_id: int, raw_selection: Optional[Dict[str, Any]]
    ) -> Tuple[Optional[ChatSelection], List[ChatSelectionWarning]]:
        """Drop from a stored selection (user default / conversation state) whatever is no longer valid.

        Never raises for invalid or retired content: such entries are dropped and reported as warnings.
        Returns ``(None, warnings)`` when nothing usable is left (no valid AI service, or unparsable data).
        """
        if not raw_selection:
            return None, []
        try:
            # Tolerant: stored data may carry keys this version does not know (future field, rollback).
            known = {k: v for k, v in dict(raw_selection).items() if k in ChatSelection.model_fields}
            selection = ChatSelection.model_validate(known)
        except (ValidationError, TypeError, ValueError):
            logger.warning("Dropping an unparsable stored chat selection for app %s", app_id)
            return None, []

        loaded = ChatSelectionResolver._load(db, app_id, selection)
        dropped: List[ChatSelectionWarning] = list(loaded.missing)
        gone = {(w.kind, w.id) for w in dropped}

        service = loaded.ai_service
        if service is not None and is_retired(service):
            dropped.append(ChatSelectionWarning(kind="ai_service", id=service.service_id))
            service = None
        silo_id = selection.silo_id
        if loaded.silo is not None and is_retired(loaded.silo.embedding_service):
            dropped.append(ChatSelectionWarning(kind="silo", id=loaded.silo.silo_id))
            silo_id = None
        elif ("silo", selection.silo_id) in gone:
            silo_id = None

        if dropped:
            logger.warning(
                "Dropped invalid entries from a stored chat selection (app %s): %s",
                app_id,
                [(w.kind, w.id) for w in dropped],
            )
        if service is None:
            return None, dropped

        found_skills = {s.skill_id for s in loaded.skills}
        found_mcp = {c.config_id for c in loaded.mcp_configs}
        return (
            ChatSelection(
                ai_service_id=selection.ai_service_id,
                silo_id=silo_id,
                skill_ids=[i for i in _dedupe(selection.skill_ids) if i in found_skills],
                mcp_config_ids=[i for i in _dedupe(selection.mcp_config_ids) if i in found_mcp],
            ),
            dropped,
        )

    @staticmethod
    def app_default(db: Session, app_id: int, services: Optional[Sequence[Any]] = None) -> Optional[ChatSelection]:
        """First usable (active or deprecated) AI service: the App's own by id, then system ones.

        ``services`` (already loaded by the caller, in ``ChatOptionsRepository.ai_services`` order) avoids a
        second query. No silo, skills or MCP. None when the App has no usable model.
        """
        candidates = services if services is not None else ChatOptionsRepository.ai_services(db, app_id)
        for service in candidates:
            if not is_retired(service):
                return ChatSelection(ai_service_id=service.service_id)
        return None
