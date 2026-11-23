"""
AgentExecutionContext — plain data container produced by _prepare_turn().

Carries every field that the execution and finalization phases need so that
_prepare_turn, _execute_agent_async, and _finalize_turn can pass state without
a growing argument list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from services.internal_chat.resolved_config import ResolvedChatConfig


@dataclass(frozen=True)
class TurnCompleted:
    """Plain-data description of a completed chat turn, handed to the completion hook.

    Holds ids and plain data only (``turn_config`` is read for its ``*_id``/``*_name`` fields;
    never touch its ORM members: they are expired by the pre-run commit).
    """

    conversation_id: Optional[int]
    assistant_message_id: Optional[str]
    user_context: Optional[Dict[str, Any]]
    turn_config: "ResolvedChatConfig"
    # Id of the agent_execution_event row of this run (metrics), when known.
    execution_event_id: Optional[str] = None


# Async hook called once per completed chat turn; returns a JSON-ready dict (exposed as
# ``result["turn"]`` / ``done.turn``) or None. See ``AgentExecutionService._finalize_turn``.
TurnCompletedHook = Callable[[TurnCompleted], Awaitable[Optional[dict]]]


@dataclass
class TurnOutcome:
    """Out-parameter of ``_execute_agent_async`` (the sync path returns only the text)."""

    assistant_message_id: Optional[str] = None
    execution_event_id: Optional[str] = None


def is_chat_turn(ctx: Any) -> bool:
    """Single rule deciding whether a context is a flexible-chat turn (tolerates bare test doubles)."""
    return getattr(ctx, "turn_config", None) is not None


def notify_before_model(turn_config: Optional["ResolvedChatConfig"]) -> None:
    """Chat turns: tell the Chat service the model is about to run (it renews the busy marker). No-op otherwise."""
    diagnostics = getattr(turn_config, "diagnostics", None)
    run = getattr(diagnostics, "run_before_model", None)
    if callable(run):
        run()


def tracing_kwargs(turn_config: Optional["ResolvedChatConfig"]) -> Dict[str, Any]:
    """Extra ``build_tracing_config`` kwargs for a chat turn (empty for every other turn)."""
    if turn_config is None:
        return {}
    return {
        "extra_metadata": turn_config.to_trace_metadata(),
        "extra_tags": ["internal_chat", f"ai_service:{turn_config.ai_service_id}"],
    }


@dataclass
class AgentExecutionContext:
    """Immutable snapshot of all setup state for one agent chat turn."""

    # Core identity
    agent_id: int
    agent: Any                          # Agent ORM instance (lightweight, pre-access-check)
    fresh_agent: Any                    # Agent ORM instance with all relationships loaded

    # Message
    enhanced_message: str               # Text message after file-content injection
    image_files: List[Dict[str, Any]]   # Image file dicts extracted from processed_files

    # Session / conversation
    session: Optional[Any] = None       # SessionManagementService session object
    conversation: Optional[Any] = None  # Conversation ORM instance (None when no memory)
    effective_conv_id: Optional[int] = None  # Resolved conversation ID (auto-created or passed)
    session_id_for_cache: Optional[str] = None  # LangGraph thread ID suffix

    # Working directory
    working_dir: Optional[str] = None
    pre_existing_files: set = field(default_factory=set)

    # Sandbox — populated when enable_code_interpreter is True for non-subprocess providers
    sandbox_handle: Optional[Any] = None           # SandboxHandle (typed as Any to avoid circular import)
    sandbox_provider: Optional[Any] = None         # SandboxProvider instance
    sandbox_session_key: Optional[str] = None      # Key used with SandboxSessionService
    pre_existing_remote_files: set = field(default_factory=set)  # Snapshot before turn for remote pull diff
    outputs_pulled: bool = False  # the sandbox output pull already ran for this turn (it runs once, before finalize)
    outputs_undelivered: int = 0  # files the pull could not deliver (limits / time / errors); counts only

    # Original inputs (needed by finalize for metadata)
    processed_files: List[Dict[str, Any]] = field(default_factory=list)
    search_params: Optional[Dict[str, Any]] = None
    user_context: Optional[Dict[str, Any]] = None

    # Flexible App chat (None for every other channel => behaviour unchanged).
    # ``turn_config`` is the frozen per-request ``ResolvedChatConfig``; its ORM members are only
    # valid inside the request Session (and are expired by the pre-run commit), so post-run code
    # must use its ``*_id`` / ``*_name`` / scalar snapshot fields.
    turn_config: Optional["ResolvedChatConfig"] = None

    @property
    def is_chat_turn(self) -> bool:
        return is_chat_turn(self)
