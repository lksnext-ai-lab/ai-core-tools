"""Build an agent's LangChain middleware chain from its configured Middleware rows.

Every type maps to a LangChain built-in (or a small middleware in this package) through
``_BUILDERS``. Stored configs are re-validated with the same Pydantic models used on
write, so a malformed row is skipped with a warning instead of breaking the chat.
"""
from typing import Any, Callable, List, Optional

from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    PIIMiddleware,
    SummarizationMiddleware,
    ToolCallLimitMiddleware,
)
from langchain_core.messages import BaseMessage, HumanMessage, trim_messages
from langchain_core.runnables.retry import RunnableRetry
from tenacity import retry_if_exception, retry_if_exception_type
from pydantic import ValidationError

from models.middleware import MiddlewareType
from schemas.middleware_schemas import HITLConfig, PIIConfig, SummarizationConfig, parse_middleware_config
from tools.middleware.guardrails import GuardrailsMiddleware
from tools.middleware.history_normalizer import HistoryNormalizerMiddleware
from tools.middleware.llm_pii import LLMPIIMiddleware
from utils.logger import get_logger

logger = get_logger(__name__)

# Summarize at 85% of the model's input window (Deep Agents default), capped at
# 150k tokens (Anthropic compaction default) so long-context models do not degrade.
# Models without a profile (custom endpoints, Ollama) use a conservative fixed trigger.
SUMMARY_TRIGGER_WINDOW_FRACTION = 0.85
SUMMARY_TRIGGER_MAX_TOKENS = 150_000
SUMMARY_TRIGGER_FALLBACK_TOKENS = 32_000
# Room kept in the summary model's window for the summary instructions (~700 tokens), the XML
# framing of every message and the summary it writes. The older history sent to the summary
# call is bounded by the summary model's default trigger minus this.
SUMMARY_PROMPT_OVERHEAD_TOKENS = 2_000
# A history over the threshold is trimmed to this share of the window (minus the overhead): the approximate
# token counter underestimates real text, and the summary the model writes needs room as well.
SUMMARY_TRIM_TARGET_WINDOW_FRACTION = 0.8
_FALLBACK_MESSAGE_COUNT = 15  # the library's fallback when trimming itself fails


def _resolve_llm(agent, ref: str, default_llm):
    """Return the LLM for an ``agent_llm`` / ``ai_service:<id>`` reference (same app only)."""
    if not ref or ref == "agent_llm":
        return default_llm
    from tools.aiServiceTools import create_llm_from_service

    service_id = int(ref.split(":", 1)[1])
    app = getattr(agent, "app", None)
    service = next((s for s in (app.ai_services if app else []) if s.service_id == service_id), None)
    if service is None:
        logger.warning("AIService %s not found in app of agent %s; using the agent LLM", service_id, agent.agent_id)
        return default_llm
    return create_llm_from_service(service, temperature=0)


def default_trigger_tokens(llm) -> int:
    """Token count that triggers summarization for the agent's model."""
    max_input = (getattr(llm, "profile", None) or {}).get("max_input_tokens")
    if isinstance(max_input, int) and max_input > 0:
        return min(int(max_input * SUMMARY_TRIGGER_WINDOW_FRACTION), SUMMARY_TRIGGER_MAX_TOKENS)
    return SUMMARY_TRIGGER_FALLBACK_TOKENS


def _model_window(llm) -> Optional[int]:
    max_input = (getattr(llm, "profile", None) or {}).get("max_input_tokens")
    return int(max_input) if isinstance(max_input, int) and max_input > 0 else None


def summary_trim_limits(
    llm, configured_trigger: Optional[int] = None, chat_turn: bool = False
) -> Optional[tuple[int, int]]:
    """``(threshold, target)`` for the older history of ONE summary call, or None for no bound.

    THRESHOLD: history up to this size is sent whole. It is the summary model's WINDOW minus the prompt
    overhead (a configured trigger above the window does not raise it: that history would overflow): the older history of a conversation that
    stayed on one model is at most about its trigger (85% of the window), so it is never trimmed; only a
    conversation that switched to a smaller-window model is.
    TARGET: where a history over the threshold is trimmed to (<= threshold). It is lower because the
    approximate token counter underestimates real text (chars / 4): trimming to the estimated limit would
    still overflow the window, and the summary output needs room too.

    Without a model profile regular agents keep the old behaviour (no bound); a Chat turn, whose thread
    may have been written by a bigger model, assumes the conservative fallback window (~37.6k).
    """
    window = _model_window(llm)
    if window is None:
        if not chat_turn:
            return None
        # The window whose 85% trigger is the fallback trigger: same-model history stays below the threshold.
        window = int(SUMMARY_TRIGGER_FALLBACK_TOKENS / SUMMARY_TRIGGER_WINDOW_FRACTION)
    overhead = min(SUMMARY_PROMPT_OVERHEAD_TOKENS, window // 2)
    threshold = window - overhead
    if configured_trigger and configured_trigger > window and _model_window(llm) is not None:
        # Sending a history that big whole would overflow the summary model: it is trimmed.
        logger.warning(
            "Configured summarization trigger (%d tokens) exceeds the summary model's window (%d tokens)",
            configured_trigger, window,
        )
    target = max(min(threshold, int(window * SUMMARY_TRIM_TARGET_WINDOW_FRACTION) - overhead), 1)
    return threshold, target


def _is_earlier_summary(message: BaseMessage) -> bool:
    """The message SummarizationMiddleware wrote for an earlier summarization (``_build_new_messages``)."""
    return isinstance(message, HumanMessage) and message.additional_kwargs.get("lc_source") == "summarization"


def _is_transient_error(exc: BaseException) -> bool:
    """False for a deterministic client error (HTTP 4xx other than 408/429), whatever the SDK.

    Read from ``status_code`` / ``response.status_code``, which the OpenAI, Anthropic, Mistral, Google and
    httpx exceptions all expose. Unknown errors count as transient (the library default).
    """
    if not isinstance(exc, Exception):
        return False  # CancelledError, KeyboardInterrupt, SystemExit: never retried (timeouts, disconnects, shutdown)
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int) and 400 <= status < 500 and status not in (408, 429):
        return False
    return True


class _TransientOnlyRetry(RunnableRetry):
    """``with_retry()`` that does not repeat deterministic 4xx failures (a 400 context overflow is not transient).

    Overrides the tenacity kwargs hook of ``RunnableRetry``; if that hook ever disappears the retry simply
    reverts to retrying every exception (the library behaviour).
    """

    @property
    def _kwargs_retrying(self) -> dict[str, Any]:
        kwargs = super()._kwargs_retrying
        # Ordinary exceptions only: tenacity hands EVERY BaseException of the attempt to the predicate.
        kwargs["retry"] = retry_if_exception_type(Exception) & retry_if_exception(_is_transient_error)
        return kwargs


class _SummarizationKeepingEarlierSummary(SummarizationMiddleware):
    """Summarization whose summary input is bounded by a threshold and a lower target (``summary_trim_limits``).

    ``trim_tokens_to_summarize`` holds the THRESHOLD. A history over it is trimmed to ``trim_target_tokens``
    (the same value when ``trim_tokens`` is configured explicitly: library behaviour), dropping the MIDDLE:
    the library's ``strategy="last"`` would drop the earlier summary (the oldest message) first and lose the
    conversation's long-term memory. If the earlier summary alone does not fit the target, or on any error,
    the plain ``strategy="last"`` trim applies (to the threshold when even that leaves nothing).
    """

    def __init__(self, *args: Any, trim_target_tokens: Optional[int] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        limit = self.trim_tokens_to_summarize
        self.trim_target_tokens = min(trim_target_tokens, limit) if (trim_target_tokens and limit) else limit
        retry = self._summary_model
        self._summary_model = _TransientOnlyRetry(
            bound=self.model, kwargs={}, config={},
            retry_exception_types=(Exception,), wait_exponential_jitter=retry.wait_exponential_jitter,
            max_attempt_number=retry.max_attempt_number,
        )

    @property
    def name(self) -> str:
        return "SummarizationMiddleware"  # keep the node / trace name of the library class

    def _trim_messages_for_summary(self, messages):
        limit, target = self.trim_tokens_to_summarize, self.trim_target_tokens
        if limit is None or not messages:
            return super()._trim_messages_for_summary(messages)
        try:
            if self.token_counter(messages) <= limit:
                return messages
            head_tokens = self.token_counter([messages[0]]) if _is_earlier_summary(messages[0]) else None
            if head_tokens is not None and head_tokens < target:
                rest = self._trim(messages[1:], target - head_tokens, include_system=False)
                return [messages[0], *rest]
            trimmed = self._trim(messages, target, include_system=True)
            # A single message larger than the target would empty the summary input and silently drop the
            # whole history ("too long to summarize"): in that case settle for what the threshold allows.
            return trimmed or self._trim(messages, limit, include_system=True)
        except Exception:
            return messages[-_FALLBACK_MESSAGE_COUNT:]

    def _trim(self, messages, max_tokens: int, include_system: bool):
        return trim_messages(
            messages,
            max_tokens=max_tokens,
            token_counter=self.token_counter,
            start_on="human",
            strategy="last",
            allow_partial=True,
            include_system=include_system,
        )


_fallback_warned = False


def _warn_summarization_fallback(exc: BaseException) -> None:
    """ONE warning (class name only) the first time the plain library summarization replaces our subclass."""
    global _fallback_warned
    if not _fallback_warned:
        _fallback_warned = True
        logger.warning(
            "Summarization: the installed langchain no longer matches what the bounded-summary subclass reads (%s); "
            "using the plain SummarizationMiddleware", type(exc).__name__,
        )


def _summarization(
    agent, llm, cfg: Optional[SummarizationConfig], chat_turn: bool = False
) -> Optional[SummarizationMiddleware]:
    """Summarization from an attached middleware, or with the defaults for agents with memory."""
    if cfg is None:
        if not agent.has_memory:
            return None
        cfg = SummarizationConfig()
    summary_llm = _resolve_llm(agent, cfg.summarization_model, llm)
    # ``None`` would send the whole older history in ONE summary call, which overflows the summary
    # model after a conversation switched to a smaller-window model (see ``summary_input_bound``).
    # An explicitly configured ``trim_tokens`` wins.
    limits = None if cfg.trim_tokens else summary_trim_limits(summary_llm, cfg.trigger_tokens, chat_turn)
    threshold, target = (cfg.trim_tokens, cfg.trim_tokens) if cfg.trim_tokens else (limits or (None, None))
    trigger = ("tokens", cfg.trigger_tokens or default_trigger_tokens(llm))
    keep = ("messages", cfg.keep_messages)
    try:
        return _SummarizationKeepingEarlierSummary(
            model=summary_llm,
            trigger=trigger,
            keep=keep,
            trim_tokens_to_summarize=threshold,
            trim_target_tokens=target,
        )
    except (AttributeError, TypeError, NameError) as exc:
        # The subclass reads private names of the installed langchain (``_summary_model`` and friends). If one was
        # renamed, an agent with memory must still be built: use the plain library middleware.
        _warn_summarization_fallback(exc)
        return SummarizationMiddleware(
            model=summary_llm, trigger=trigger, keep=keep, trim_tokens_to_summarize=threshold,
        )


def _pii(agent, llm, cfg: PIIConfig) -> List[Any]:
    # PIIMiddleware handles one PII type per instance (its name includes the type).
    chain: List[Any] = [
        PIIMiddleware(
            pii_type,
            strategy=cfg.strategy,
            apply_to_input=cfg.apply_to_input,
            apply_to_output=cfg.apply_to_output,
            apply_to_tool_results=cfg.apply_to_tool_results,
        )
        for pii_type in cfg.pii_types
    ]
    detector = cfg.llm_detector
    if detector and detector.enabled:
        chain.append(LLMPIIMiddleware(
            llm=_resolve_llm(agent, detector.ai_service, llm),
            entities=list(cfg.pii_types) + detector.extra_entities,
            strategy=cfg.strategy,
            apply_to_input=cfg.apply_to_input,
            apply_to_output=cfg.apply_to_output,
            apply_to_tool_results=cfg.apply_to_tool_results,
        ))
    return chain


_BUILDERS: dict[MiddlewareType, Callable[[Any, Any, Any], List[Any]]] = {
    MiddlewareType.MODEL_CALL_LIMIT: lambda agent, llm, cfg: [ModelCallLimitMiddleware(run_limit=cfg.max_calls)],
    MiddlewareType.TOOL_CALL_LIMIT: lambda agent, llm, cfg: [ToolCallLimitMiddleware(run_limit=cfg.max_calls)],
    MiddlewareType.PII: _pii,
    MiddlewareType.HUMAN_IN_THE_LOOP: lambda agent, llm, cfg: [HumanInTheLoopMiddleware(
        interrupt_on={name: {"allowed_decisions": tool.allowed_decisions} for name, tool in cfg.interrupt_on.items()},
        description_prefix=cfg.description_prefix,
    )],
    MiddlewareType.GUARDRAILS: lambda agent, llm, cfg: [GuardrailsMiddleware(cfg)],
}


def build_agent_middlewares(
    agent, llm, include_human_approval: bool = True, ignore_agent_middlewares: bool = False,
    chat_turn: bool = False,
    service_id: Optional[int] = None,
    model_name: Optional[str] = None,
    turn_diagnostics: Any = None,
) -> List[Any]:
    """Return the ordered middleware list for ``create_agent``.

    Summarization always goes first (it trims history before any other hook sees it);
    the rest follow the agent's configured order. Only one middleware of each type is
    used, matching LangChain's requirement of unique middleware instances.

    ``include_human_approval=False`` is for runs that cannot pause (an agent used as a
    tool): the caller must then withhold the gated tools (see ``tools_needing_approval``).

    ``ignore_agent_middlewares=True`` (flexible chat) skips the agent's configured
    middleware rows entirely and builds only the default summarization.

    ``chat_turn=True`` (flexible chat, whose thread can switch model between turns) appends
    ``HistoryNormalizerMiddleware`` LAST (it sees the final message list; ``service_id`` / ``model_name`` are
    the turn's frozen service snapshot, used to stamp and recognise the messages each model wrote) and bounds the
    summary input even for models without a profile. Regular agents keep a fixed model and the
    approval-recovery path, so they get neither.
    """
    configured: list[tuple[MiddlewareType, Any]] = []
    seen: set[MiddlewareType] = set()
    for assoc in ([] if ignore_agent_middlewares else getattr(agent, "middleware_associations", None) or []):
        mw = assoc.middleware
        if mw is None or mw.middleware_type in seen:
            continue
        try:
            cfg = parse_middleware_config(mw.middleware_type, mw.config)
        except ValidationError as exc:
            logger.warning("Skipping middleware %s of agent %s: invalid config (%s)",
                           mw.middleware_id, agent.agent_id, exc.errors()[0].get("msg"))
            continue
        seen.add(mw.middleware_type)
        configured.append((mw.middleware_type, cfg))

    summarization_cfg = next((c for t, c in configured if t == MiddlewareType.SUMMARIZATION), None)
    chain: List[Any] = []
    summarization = _summarization(agent, llm, summarization_cfg, chat_turn=chat_turn)
    if summarization is not None:
        chain.append(summarization)

    for mw_type, cfg in configured:
        if mw_type == MiddlewareType.SUMMARIZATION:
            continue
        if mw_type == MiddlewareType.HUMAN_IN_THE_LOOP and not include_human_approval:
            continue
        chain.extend(_BUILDERS[mw_type](agent, llm, cfg))

    if chat_turn:
        chain.append(HistoryNormalizerMiddleware(
            patch_interrupted_tool_calls=True,
            service_id=service_id,
            model_name=model_name,
        ))
        if turn_diagnostics is not None:
            from tools.middleware.chat_tool_log import ChatToolCallLogMiddleware

            chain.append(ChatToolCallLogMiddleware(turn_diagnostics))

    if configured:
        logger.info("Agent %s middleware chain: %s", agent.agent_id, [m.name for m in chain])
    return chain


def tools_needing_approval(agent) -> set[str]:
    """Names of the tools the agent's human-approval middleware gates."""
    config = human_in_the_loop_config(agent)
    return set(config.interrupt_on) if config else set()


def human_in_the_loop_config(agent) -> Optional[HITLConfig]:
    """The validated HITL config attached to the agent, if any."""
    for assoc in getattr(agent, "middleware_associations", None) or []:
        mw = assoc.middleware
        if mw is not None and mw.middleware_type == MiddlewareType.HUMAN_IN_THE_LOOP:
            try:
                return parse_middleware_config(mw.middleware_type, mw.config)
            except ValidationError:
                return None
    return None


def redacts_output(agent) -> bool:
    """True when a PII middleware must redact model output before the user sees it."""
    for assoc in getattr(agent, "middleware_associations", None) or []:
        mw = assoc.middleware
        if mw is not None and mw.middleware_type == MiddlewareType.PII:
            try:
                return bool(parse_middleware_config(mw.middleware_type, mw.config).apply_to_output)
            except ValidationError:
                return False
    return False

