"""
Monitoring middleware — tracks token usage and LLM call count per agent run.

Mirrors the guardrails.py pattern: a self-contained AgentMiddleware, no
external callback wiring required from the caller.

* **awrap_model_call**: reads ``AIMessage.usage_metadata`` off each model
  response (the same field LangChain's own ``UsageMetadataCallbackHandler``
  reads) and accumulates it per model name.

* **after_agent**: once the run completes, emits the ``[Monitoring]`` log
  line, filtered to the metrics enabled in config (default: all on).

HITL pause/resume note: a HITL interrupt splits one logical turn into two
separate ``create_agent()`` builds (the graph is rebuilt from scratch to
resume), which would otherwise reset ``call_count``/``usage_by_model`` to
zero for the post-approval half and silently drop the pre-approval half
(``after_agent`` never runs on an interrupted graph). ``_PENDING_STATE``
below carries the accumulated totals across that gap, keyed by the same
thread_id the checkpointer itself uses to correlate the pause and resume.
"""
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages.ai import add_usage
from utils.logger import get_logger

logger = get_logger(__name__)

# ponytail: in-process dict, not shared across worker processes and never
# cleaned up if a HITL interrupt is abandoned (never resumed). Fine for a
# single-worker deployment; revisit with a TTL or checkpointer-backed store
# if abandoned interrupts pile up in a multi-worker deployment.
_PENDING_STATE: dict[str, dict] = {}


def build_monitoring_log_line(agent_id: int, usage_by_model: dict, call_count: int, metrics_cfg: dict) -> str | None:
    """Build the ``[Monitoring] ...`` log line, filtered to enabled metrics.

    Returns None if nothing is enabled (so the caller can skip logging).
    """
    def enabled(key: str) -> bool:
        return metrics_cfg.get(key, True)  # missing flag => metric is on

    parts: list[str] = [f"[Monitoring] agent_id={agent_id}"]

    if enabled("models"):
        parts.append(f"models={list(usage_by_model.keys())}")
    if enabled("input_tokens"):
        parts.append(f"input_tokens={sum(u.get('input_tokens', 0) for u in usage_by_model.values())}")
    if enabled("output_tokens"):
        parts.append(f"output_tokens={sum(u.get('output_tokens', 0) for u in usage_by_model.values())}")
    if enabled("total_tokens"):
        parts.append(f"total_tokens={sum(u.get('total_tokens', 0) for u in usage_by_model.values())}")
    if enabled("llm_calls"):
        parts.append(f"llm_calls={call_count}")

    return " | ".join(parts) if len(parts) > 1 else None


class MonitoringMiddleware(AgentMiddleware):
    """Middleware that tracks token usage and LLM call count for an agent run.

    No extra LLM calls are made; usage is read off the real model responses
    as they pass through ``awrap_model_call``.
    """

    def __init__(self, agent_id: int, config: dict, thread_id: str | None = None) -> None:
        self._agent_id = agent_id
        self._metrics_cfg = (config or {}).get("metrics", {})
        self._thread_id = thread_id

        # Resume after a HITL interrupt: pick up where the discarded pre-interrupt
        # instance left off instead of starting back at zero.
        pending = _PENDING_STATE.pop(thread_id, None) if thread_id else None
        self.usage_by_model: dict = dict(pending["usage_by_model"]) if pending else {}
        self.call_count = pending["call_count"] if pending else 0

        logger.info(f"[Monitoring] Initialized for agent {agent_id} — metrics={self._metrics_cfg or 'all'}")

    async def awrap_model_call(self, request, handler):
        response = await handler(request)
        # Count the invocation itself — usage_metadata may be absent for some
        # providers/fakes, but the LLM was still called once.
        self.call_count += 1

        for message in response.result:
            usage = getattr(message, "usage_metadata", None)
            model_name = (getattr(message, "response_metadata", None) or {}).get("model_name")
            if usage and model_name:
                self.usage_by_model[model_name] = add_usage(self.usage_by_model.get(model_name), usage)

        # Snapshot after every call so a HITL interrupt right after this point
        # (after_agent never runs on a paused graph) doesn't lose these totals.
        if self._thread_id:
            _PENDING_STATE[self._thread_id] = {
                "usage_by_model": dict(self.usage_by_model),
                "call_count": self.call_count,
            }

        return response

    def after_agent(self, state: dict, runtime: object) -> dict | None:
        line = build_monitoring_log_line(self._agent_id, self.usage_by_model, self.call_count, self._metrics_cfg)
        if line:
            logger.info(line)
        if self._thread_id:
            _PENDING_STATE.pop(self._thread_id, None)
        return None
