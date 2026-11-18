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

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from schemas.internal_chat_schemas import ChatSelectionWarning


class InternalChatSessionError(RuntimeError):
    """Raised when an internal-chat turn has no conversation session.

    The Chat must never fall back to the shared ``"default"`` session or to the
    agent-wide ``thread_{agent_id}`` checkpointer thread: that would mix the history of
    different users/conversations.
    """


@dataclass(frozen=True, slots=True)
class MetricsServiceInfo:
    """Plain-data stand-in for an AIService in the metrics payload (no ORM access)."""

    service_id: int
    provider: str | None
    description: str | None


@dataclass(frozen=True, slots=True)
class McpConnectionSpec:
    """One MCP config resolved for a turn (``connections`` is a private deep copy)."""

    config_id: int
    name: str
    connections: Mapping[str, Any] = field(repr=False)  # MCPConfig.to_connection_dict(), deep-copied
    ssl_verify: bool


class TurnDiagnostics:
    """Per-turn carrier for what only becomes known while the agent is built (one instance per ``ResolvedChatConfig``).

    ``ResolvedChatConfig`` is frozen, so tool building cannot add to it; instead it reports here, and the completion
    hook of the same turn reads it. The object is created with the config (one per request, never shared between
    turns or users) and holds ids only.
    """

    __slots__ = (
        "mcp_unavailable_ids", "before_model", "sandbox_degraded", "outputs_skipped",
        "step_limit_reached", "model_calls", "tool_counts", "conversation_id", "turn_id", "renew_marker",
    )

    def __init__(self) -> None:
        self.mcp_unavailable_ids: list[int] = []
        # Set by the Chat service: called (synchronously, never raising) right before the model runs.
        self.before_model: Callable[[], None] | None = None
        # Set by the Chat service: renews the busy marker, returns False when the marker was lost (aborts the turn).
        self.renew_marker: Callable[[], bool] | None = None
        # Set by ``_prepare_turn`` when the turn was configured with a code interpreter but could not get one.
        self.sandbox_degraded: bool = False
        # Output files the sandbox pull skipped (size / count / time limits, errors); 0 = nothing skipped.
        self.outputs_skipped: int = 0
        # The turn ended with the graph step limit: the conversation / checkpoint / sandbox are kept.
        self.step_limit_reached: bool = False
        # Counts only (written by the chat tool-call log middleware; never names of arguments or outputs).
        self.model_calls: int = 0
        self.tool_counts: dict[str, int] = {}
        self.conversation_id: int | None = None
        self.turn_id: str = uuid.uuid4().hex[:8]  # short correlation id of this turn's log lines

    def run_before_model(self) -> None:
        """Run the ``before_model`` hook, if any (the execution / streaming services call this)."""
        hook = self.before_model
        if hook is not None:
            hook()

    def report_outputs_skipped(self, count: int) -> None:
        """Output files not delivered this turn (counts only, never names)."""
        self.outputs_skipped = max(self.outputs_skipped, int(count))

    def reset(self) -> None:
        """Forget earlier reports (a retried agent build starts its MCP load afresh)."""
        self.mcp_unavailable_ids.clear()

    def report_mcp_unavailable(self, config_ids: tuple[int, ...] | list[int]) -> None:
        """The selected MCP configs whose tools could not be loaded for this turn (connect failure / timeout)."""
        for config_id in config_ids:
            if config_id not in self.mcp_unavailable_ids:
                self.mcp_unavailable_ids.append(config_id)


@dataclass(frozen=True, slots=True)
class ResolvedChatConfig:
    app_id: int
    ai_service: Any = field(repr=False, compare=False)  # AIService ORM, loaded and validated
    ai_service_id: int
    ai_service_name: str
    # Plain snapshots of the AIService attributes read AFTER the LLM run (quota, metrics). Post-run
    # code must never touch ``ai_service``: it is expired by the pre-run commit and a service
    # deleted mid-turn would raise ``ObjectDeletedError`` on a turn that already completed.
    ai_service_is_system: bool  # AIService.app_id IS NULL (platform-owned => counts against quota)
    ai_service_provider: str | None
    ai_service_model: str | None  # AIService.description (the configured model name)
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
    # Selected MCP configs skipped for this turn (unusable connection config): ids only, for the SSE metadata.
    skipped_mcp_config_ids: tuple[int, ...] = ()
    # Code interpreter: ``sandbox_enabled`` = the App switch is on and a usable source was resolved (the App default
    # service, or - ``sandbox_service_id is None`` - the system default like agents). Otherwise the turn runs without
    # code interpreter. The ORM object is only valid within the resolving Session; id / name / provider are snapshots.
    sandbox_enabled: bool = False
    sandbox_service: Any | None = field(default=None, repr=False, compare=False)
    sandbox_service_id: int | None = None
    sandbox_service_name: str | None = None
    sandbox_provider: str | None = None
    # Mutable per-turn carrier (not part of equality / repr): see ``TurnDiagnostics``.
    diagnostics: TurnDiagnostics = field(default_factory=TurnDiagnostics, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Fail loudly: a missing service or a non-tuple would otherwise make downstream
        # code silently fall back to the shared agent's own configuration.
        if self.ai_service is None:
            raise ValueError("ResolvedChatConfig.ai_service is required")
        if not isinstance(self.skills, tuple):
            raise TypeError("ResolvedChatConfig.skills must be a tuple")
        if not isinstance(self.mcp_connections, tuple):
            raise TypeError("ResolvedChatConfig.mcp_connections must be a tuple")

    def code_interpreter_active(self) -> bool:
        """True when the turn really had a code interpreter (configured AND ``_prepare_turn`` did not degrade)."""
        return self.sandbox_enabled and not self.diagnostics.sandbox_degraded

    def metrics_service(self) -> MetricsServiceInfo:
        """The turn's AI service as plain data, safe to read after the run / session."""
        return MetricsServiceInfo(
            service_id=self.ai_service_id,
            provider=self.ai_service_provider,
            description=self.ai_service_model,
        )

    def to_client_summary(self) -> dict:
        """Ids and display names only, for the SSE ``metadata`` event."""
        summary = {
            "ai_service": {"id": self.ai_service_id, "name": self.ai_service_name},
            "silo": {"id": self.silo_id, "name": self.silo_name} if self.silo_id is not None else None,
            "skills": [{"id": i, "name": n} for i, n in zip(self.skill_ids, self.skill_names)],
            "mcp_configs": [{"id": i, "name": n} for i, n in zip(self.mcp_config_ids, self.mcp_config_names)],
        }
        # Whether the turn had a code interpreter (ids/names only, no provider credentials).
        summary["code_interpreter"] = self.code_interpreter_active()
        # Always present (empty when nothing was skipped); same shape as ``ChatTurnInfo.warnings``.
        summary["warnings"] = [
            ChatSelectionWarning(kind="mcp_config", id=i).model_dump() for i in self.skipped_mcp_config_ids
        ]
        return summary

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
            "chat_code_interpreter": self.code_interpreter_active(),
            "chat_sandbox_service_id": self.sandbox_service_id,
            "chat_sandbox_provider": self.sandbox_provider,
        }
