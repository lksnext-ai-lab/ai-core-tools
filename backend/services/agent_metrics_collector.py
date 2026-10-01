"""LangChain callback handler that collects per-execution metrics.

Attached to an agent run's config, it sees every LLM and tool call of the run,
including the ones a sub-agent makes (callbacks propagate into tools). Only the
agent's *direct* calls are kept: anything under an AGENT tool run belongs to the
sub-agent, which records its own execution event — counting it here too would
double the totals.
"""
from collections import Counter
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

# Tool metadata keys set by tools.agentTools when building an agent's tools.
# METRICS_TOOL_TYPE_KEY values are AgentToolCallType names.
METRICS_TOOL_TYPE_KEY = "mattin_tool_type"
METRICS_SUB_AGENT_ID_KEY = "mattin_sub_agent_id"

MAX_TOOL_CALLS = 200
_ERROR_MESSAGE_MAX = 2000


class AgentMetricsCollector(BaseCallbackHandler):
    """Accumulates LLM usage and tool calls for one agent execution."""

    # Plain dict bookkeeping: run in the event loop, never in an executor thread.
    run_inline = True
    raise_error = False

    def __init__(self) -> None:
        self._parents: dict[UUID, Optional[UUID]] = {}
        self._agent_tool_runs: set[UUID] = set()
        self._open_tools: dict[UUID, dict[str, Any]] = {}
        self.llm_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self._usage_seen = False
        self._models: Counter[str] = Counter()
        self.tool_calls: list[dict[str, Any]] = []

    # ── derived values ────────────────────────────────────────────────────

    @property
    def model_name(self) -> Optional[str]:
        """The model that served most of the direct LLM calls."""
        return self._models.most_common(1)[0][0] if self._models else None

    def token_usage(self) -> tuple[Optional[int], Optional[int], Optional[int]]:
        """(input, output, total) summed over direct LLM calls; Nones if no call reported usage."""
        if not self._usage_seen:
            return None, None, None
        return self.input_tokens, self.output_tokens, self.total_tokens

    # ── run tree ──────────────────────────────────────────────────────────

    def _track(self, run_id: UUID, parent_run_id: Optional[UUID]) -> None:
        self._parents[run_id] = parent_run_id

    def _is_nested(self, run_id: UUID) -> bool:
        """True when the run executes inside a sub-agent (an AGENT tool run is an ancestor)."""
        current = self._parents.get(run_id)
        seen = set()
        while current is not None and current not in seen:
            if current in self._agent_tool_runs:
                return True
            seen.add(current)
            current = self._parents.get(current)
        return False

    # ── chains ────────────────────────────────────────────────────────────

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs) -> None:
        self._track(run_id, parent_run_id)

    # ── LLM calls ─────────────────────────────────────────────────────────

    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, **kwargs) -> None:
        self._track(run_id, parent_run_id)

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, **kwargs) -> None:
        self._track(run_id, parent_run_id)

    def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs) -> None:
        self._track(run_id, parent_run_id)
        if self._is_nested(run_id):
            return
        self.llm_calls += 1
        message = _first_message(response)
        usage = getattr(message, "usage_metadata", None) or _llm_output_usage(response)
        if usage:
            self._usage_seen = True
            inp = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
            out = usage.get("output_tokens") or usage.get("completion_tokens") or 0
            self.input_tokens += inp
            self.output_tokens += out
            self.total_tokens += usage.get("total_tokens") or (inp + out)
        metadata = getattr(message, "response_metadata", None) or {}
        model = metadata.get("model_name") or metadata.get("model") or (response.llm_output or {}).get("model_name")
        if model:
            self._models[str(model)] += 1

    def on_llm_error(self, error, *, run_id, parent_run_id=None, **kwargs) -> None:
        self._track(run_id, parent_run_id)
        if not self._is_nested(run_id):
            self.llm_calls += 1

    # ── tool calls ────────────────────────────────────────────────────────

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, metadata=None, **kwargs) -> None:
        self._track(run_id, parent_run_id)
        metadata = metadata or {}
        tool_type = metadata.get(METRICS_TOOL_TYPE_KEY) or "BUILTIN"
        if tool_type == "AGENT":
            self._agent_tool_runs.add(run_id)
        if self._is_nested(run_id):
            return
        self._open_tools[run_id] = {
            "tool_name": (serialized or {}).get("name") or kwargs.get("name") or "unknown",
            "tool_type": tool_type,
            "sub_agent_id": metadata.get(METRICS_SUB_AGENT_ID_KEY) if tool_type == "AGENT" else None,
            "started": datetime.utcnow(),
        }

    def on_tool_end(self, output, *, run_id, parent_run_id=None, **kwargs) -> None:
        # A tool error handled by the tool itself (handle_tool_error) ends normally
        # with an error ToolMessage for the model; it is still an ERROR here.
        if getattr(output, "status", None) == "error":
            self._close_tool(run_id, "ERROR", str(getattr(output, "content", ""))[:_ERROR_MESSAGE_MAX])
            return
        self._close_tool(run_id, "SUCCESS", None)

    def on_tool_error(self, error, *, run_id, parent_run_id=None, **kwargs) -> None:
        self._close_tool(run_id, "ERROR", f"{type(error).__name__}: {error}"[:_ERROR_MESSAGE_MAX])

    def _close_tool(self, run_id: UUID, status: str, error_message: Optional[str]) -> None:
        opened = self._open_tools.pop(run_id, None)
        if opened is None or len(self.tool_calls) >= MAX_TOOL_CALLS:
            return
        started = opened.pop("started")
        self.tool_calls.append({
            **opened,
            "mcp_config_id": None,
            "status": status,
            "error_message": error_message,
            "duration_ms": int((datetime.utcnow() - started).total_seconds() * 1000),
            "started_at": started.isoformat(),
        })


def _first_message(response: Any) -> Any:
    try:
        return response.generations[0][0].message
    except (AttributeError, IndexError, TypeError):
        return None


def _llm_output_usage(response: Any) -> Optional[dict]:
    """Fallback for providers that only report usage in llm_output."""
    usage = (getattr(response, "llm_output", None) or {}).get("token_usage")
    return usage if isinstance(usage, dict) else None
