"""Metrics instrumentation hook contract for Mattin AI core.

This module defines the payload types and the registration mechanism used by
the mattin-metrics plugin. The core never imports the plugin directly; instead
the plugin calls register_execution_hook() during register() to replace the
no-op with its own implementation.
"""
from typing import Optional, Callable, Awaitable, TypedDict
import uuid as _uuid


class AgentToolCallPayload(TypedDict):
    tool_name: str
    tool_type: str          # AgentToolCallType value
    sub_agent_id: Optional[int]
    mcp_config_id: Optional[int]
    duration_ms: Optional[int]
    status: str             # AgentToolCallStatus value
    error_message: Optional[str]
    started_at: str         # ISO-8601 UTC


class AgentExecutionEventPayload(TypedDict):
    event_id: str           # UUID str
    app_id: int
    agent_id: int
    conversation_id: Optional[int]
    user_id: Optional[int]
    api_key_id: Optional[int]
    caller_type: str        # AgentExecutionCallerType value
    parent_execution_id: Optional[str]
    started_at: str         # ISO-8601 UTC
    finished_at: Optional[str]
    duration_ms: Optional[int]
    status: str             # AgentExecutionStatus value
    error_code: Optional[str]
    error_message: Optional[str]
    model_name: Optional[str]
    ai_service_id: Optional[int]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int]
    tool_calls: Optional[list]       # capped JSON summary
    retrieved_docs: Optional[list]
    had_files: bool
    file_count: int
    had_images: bool
    output_parser_used: bool
    parser_succeeded: Optional[bool]
    prompt_chars: Optional[int]
    response_chars: Optional[int]


class MetricsHookPayload(TypedDict):
    event: AgentExecutionEventPayload
    tool_calls: list  # list[AgentToolCallPayload]


# Module-level hook slot. None = no-op (OSS default).
_execution_hook: Optional[Callable[[MetricsHookPayload], Awaitable[None]]] = None


def register_execution_hook(fn: Callable[[MetricsHookPayload], Awaitable[None]]) -> None:
    """Replace the no-op hook with the provided async callable."""
    global _execution_hook
    _execution_hook = fn


def get_execution_hook() -> Optional[Callable[[MetricsHookPayload], Awaitable[None]]]:
    """Return the current hook (None if not registered)."""
    return _execution_hook
