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
from pydantic import ValidationError

from models.agent import DEFAULT_MEMORY_SUMMARIZE_THRESHOLD
from models.middleware import MiddlewareType
from schemas.middleware_schemas import HITLConfig, PIIConfig, SummarizationConfig, parse_middleware_config
from tools.middleware.guardrails import GuardrailsMiddleware
from tools.middleware.llm_pii import LLMPIIMiddleware
from utils.logger import get_logger

logger = get_logger(__name__)


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


def _summarization(agent, llm, cfg: Optional[SummarizationConfig]) -> Optional[SummarizationMiddleware]:
    """Summarization from an attached middleware, or from the agent's memory settings."""
    if cfg is not None:
        return SummarizationMiddleware(
            model=_resolve_llm(agent, cfg.summarization_model, llm),
            trigger=("tokens", cfg.trigger_tokens),
            keep=("messages", cfg.keep_messages),
            trim_tokens_to_summarize=cfg.trim_tokens,
        )
    if agent.has_memory:
        return SummarizationMiddleware(
            model=llm,
            trigger=("tokens", agent.memory_max_tokens or 4000),
            keep=("messages", agent.memory_max_messages or 20),
            trim_tokens_to_summarize=agent.memory_summarize_threshold or DEFAULT_MEMORY_SUMMARIZE_THRESHOLD,
        )
    return None


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


def build_agent_middlewares(agent, llm) -> List[Any]:
    """Return the ordered middleware list for ``create_agent``.

    Summarization always goes first (it trims history before any other hook sees it);
    the rest follow the agent's configured order. Only one middleware of each type is
    used, matching LangChain's requirement of unique middleware instances.
    """
    configured: list[tuple[MiddlewareType, Any]] = []
    seen: set[MiddlewareType] = set()
    for assoc in getattr(agent, "middleware_associations", None) or []:
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
    summarization = _summarization(agent, llm, summarization_cfg)
    if summarization is not None:
        chain.append(summarization)

    for mw_type, cfg in configured:
        if mw_type == MiddlewareType.SUMMARIZATION:
            continue
        chain.extend(_BUILDERS[mw_type](agent, llm, cfg))

    if configured:
        logger.info("Agent %s middleware chain: %s", agent.agent_id, [m.name for m in chain])
    return chain


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

