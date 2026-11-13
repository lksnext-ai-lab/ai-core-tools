"""Per-turn, validated configuration of the flexible App chat.

``ResolvedChatConfig`` is built once per turn by the service layer (after the client's
selection has been validated against the App) and threaded *explicitly* through
``create_agent`` / execution / metrics. It is frozen and never assigned onto the ORM
``Agent`` — the hidden internal-chat agent row is shared by every user of the App, so any
attribute written on it would leak between concurrent turns.

Lifetime and usage rules:

* ``ai_service``, ``silo``, ``skills`` (ORM objects) are only valid within the SQLAlchemy
  Session that resolved them. Post-turn hooks, logs and anything outliving that session
  must use the ``*_id`` / ``*_name`` fields or ``to_trace_metadata()``.
* ``repr()`` hides ORM objects and MCP connections (they can hold credentials).
* ``InternalChatSessionError`` signals a caller bug; HTTP-facing callers validate the
  conversation first so users never see it.
* Any future cache MUST key on ``(app_id, to_selection_dict())``, never on this object.

This module deliberately has no database imports and must stay import-light (it is
imported by ``tools.agentTools``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


class InternalChatSessionError(RuntimeError):
    """Raised when an internal-chat turn has no conversation session.

    The Chat must never fall back to the shared ``"default"`` session or to the
    agent-wide ``thread_{agent_id}`` checkpointer thread: that would mix the history of
    different users/conversations.
    """


@dataclass(frozen=True, slots=True)
class McpConnectionSpec:
    """One MCP config resolved for a turn (``connections`` is a private deep copy)."""

    config_id: int
    name: str
    connections: Mapping[str, Any] = field(repr=False)  # MCPConfig.to_connection_dict(), deep-copied
    ssl_verify: bool


@dataclass(frozen=True, slots=True)
class ResolvedChatConfig:
    app_id: int
    ai_service: Any = field(repr=False, compare=False)  # AIService ORM, loaded and validated
    ai_service_id: int
    ai_service_name: str
    silo: Any | None = field(repr=False, compare=False)  # Silo ORM with embedding_service loaded, or None
    silo_id: int | None
    silo_name: str | None
    skills: tuple[Any, ...] = field(repr=False, compare=False)  # Skill ORM, already filtered
    skill_ids: tuple[int, ...]
    skill_names: tuple[str, ...]
    mcp_connections: tuple[McpConnectionSpec, ...] = field(repr=False, compare=False)
    mcp_config_ids: tuple[int, ...]
    mcp_config_names: tuple[str, ...]
    system_prompt: str

    def __post_init__(self) -> None:
        # Fail loudly: a missing service or a non-tuple would otherwise make downstream
        # code silently fall back to the shared agent's own configuration.
        if self.ai_service is None:
            raise ValueError("ResolvedChatConfig.ai_service is required")
        if not isinstance(self.skills, tuple):
            raise TypeError("ResolvedChatConfig.skills must be a tuple")
        if not isinstance(self.mcp_connections, tuple):
            raise TypeError("ResolvedChatConfig.mcp_connections must be a tuple")

    def to_selection_dict(self) -> dict:
        """Selection in the persisted/client shape (``ChatSelection`` fields)."""
        return {
            "ai_service_id": self.ai_service_id,
            "silo_id": self.silo_id,
            "skill_ids": list(self.skill_ids),
            "mcp_config_ids": list(self.mcp_config_ids),
        }

    def to_trace_metadata(self) -> dict:
        """Ids and names for LangSmith / logs. Never includes secrets or connections."""
        return {
            "chat_app_id": self.app_id,
            "chat_ai_service_id": self.ai_service_id,
            "chat_ai_service_name": self.ai_service_name,
            "chat_silo_id": self.silo_id,
            "chat_silo_name": self.silo_name,
            "chat_skill_ids": list(self.skill_ids),
            "chat_skill_names": list(self.skill_names),
            "chat_mcp_config_ids": list(self.mcp_config_ids),
            "chat_mcp_config_names": list(self.mcp_config_names),
        }
