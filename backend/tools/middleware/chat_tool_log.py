"""App Chat only: one INFO line per executed tool call, counts for the step-limit summary. Never any content.

Logged: ``tool=<name> n=<index within the turn> outcome=<ok|error:<ExceptionClassName>> ms=<duration>`` plus the
conversation id and the turn's correlation id. Never the arguments, never the output, never an exception text.
"""
from __future__ import annotations

import time
from typing import Any

from langchain.agents.middleware import AgentMiddleware

from utils.logger import get_logger

logger = get_logger(__name__)


class ChatToolCallLogMiddleware(AgentMiddleware):
    """Counts model calls and tool calls into the turn diagnostics and logs each tool call without content."""

    def __init__(self, diagnostics: Any) -> None:
        super().__init__()
        self._diag = diagnostics
        self._n = 0

    @property
    def name(self) -> str:  # unique middleware name
        return "ChatToolCallLogMiddleware"

    # -- model calls: counted in the wrap hooks (``before_model`` would add a graph NODE, i.e. extra graph steps
    # per model call, shrinking the number of model calls a turn gets under the recursion limit)
    def wrap_model_call(self, request, handler):  # noqa: D102
        self._diag.model_calls += 1
        return handler(request)

    async def awrap_model_call(self, request, handler):  # noqa: D102
        self._diag.model_calls += 1
        return await handler(request)

    # -- tool calls
    def _begin(self, request) -> tuple[str, int, float]:
        tool_name = str((request.tool_call or {}).get("name") or "unknown")
        self._n += 1
        self._diag.tool_counts[tool_name] = self._diag.tool_counts.get(tool_name, 0) + 1
        return tool_name, self._n, time.monotonic()

    def _log(self, tool_name: str, n: int, started: float, outcome: str) -> None:
        logger.info(
            "chat tool=%s n=%d outcome=%s ms=%d conversation_id=%s turn=%s",
            tool_name, n, outcome, int((time.monotonic() - started) * 1000),
            self._diag.conversation_id, self._diag.turn_id,
        )

    @staticmethod
    def _outcome(result: Any) -> str:
        return "error:ToolError" if getattr(result, "status", None) == "error" else "ok"

    def wrap_tool_call(self, request, handler):  # noqa: D102
        tool_name, n, started = self._begin(request)
        try:
            result = handler(request)
        except Exception as exc:
            self._log(tool_name, n, started, f"error:{type(exc).__name__}")
            raise
        self._log(tool_name, n, started, self._outcome(result))
        return result

    async def awrap_tool_call(self, request, handler):  # noqa: D102
        tool_name, n, started = self._begin(request)
        try:
            result = await handler(request)
        except Exception as exc:
            self._log(tool_name, n, started, f"error:{type(exc).__name__}")
            raise
        self._log(tool_name, n, started, self._outcome(result))
        return result
