"""
AgentExecutionContext — plain data container produced by _prepare_turn().

Carries every field that the execution and finalization phases need so that
_prepare_turn, _execute_agent_async, and _finalize_turn can pass state without
a growing argument list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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

    # Original inputs (needed by finalize for metadata)
    original_message: str = ""                      # Raw user message before file injection
    processed_files: List[Dict[str, Any]] = field(default_factory=list)
    search_params: Optional[Dict[str, Any]] = None
    user_context: Optional[Dict[str, Any]] = None
