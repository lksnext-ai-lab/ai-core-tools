"""Make the user's chat-filter selection explicit to an orchestrator agent.

End-user chat filters (``Agent.exposed_chat_filters`` + ``search_params["filter"]``)
already scope every sub-agent's retrieval through Gate 1 / Gate 2 in
:mod:`tools.agentTools`.  The orchestrator LLM, however, never saw them: sub-agent
tool descriptions come straight from ``Agent.description`` and carry nothing about
metadata.  So an orchestrator fans out to every sub-agent even when the selection
plainly points at one of them — each irrelevant call costs a full LLM round-trip and
returns nothing useful.

This module renders an ``<active_chat_filters>`` block for the orchestrator's system
prompt: it states the selection and instructs the model to route on it.  Deciding
WHICH sub-agent a selection implies is left to the model, which can weigh the
selection against each tool's name and description — in practice the exposed metadata
fields line up with what each sub-agent is for (a ``source_type`` of ``SAT`` and a
sub-agent that handles SAT tickets).

The block is advisory: every sub-agent tool is still built and still callable.
"""

from typing import Any, Dict, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

# Mirrors _MAX_DESCRIPTION_LENGTH in retriever_tool_builder: the block must not be
# able to crowd out the agent's own system prompt.
_MAX_BLOCK_LENGTH = 2000

# Cap on filters listed, so a pathological selection cannot bloat the prompt.
_MAX_LISTED_FILTERS = 25


def _render_value(value: Any) -> str:
    """Render a filter value for prompt text.

    Strings are sanitized and quoted; other scalars are rendered bare (``is_active =
    true``).  Sanitization is MANDATORY: the public ``/call`` API accepts an arbitrary
    ``Dict[str, Any]`` as ``search_params["filter"]``, and this block places those
    values in the SYSTEM PROMPT — a surface that did not exist when they only ever
    became ``$eq`` clauses.
    """
    from tools.vector_stores.metadata_filters import sanitize_metadata_value  # noqa: PLC0415

    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return f'"{sanitize_metadata_value(str(value), max_len=100)}"'


def render_chat_filter_block(
    active_filter: Dict[str, Any],
    has_subagents: bool,
) -> str:
    """Render the ``<active_chat_filters>`` block. Pure — no I/O. Never raises.

    Args:
        active_filter: Flat ``{field: value}`` already whitelisted by Gate 1.
        has_subagents: Whether the agent has sub-agent tools. The routing instruction
            is only emitted when it does — for a plain agent the announcement alone is
            what is useful (its own retrieval is scoped, so it should neither repeat
            the filter in its query nor report the excluded data as missing).

    Returns:
        The block, or ``""`` when there is no selection to announce.
    """
    if not active_filter:
        return ""

    from tools.vector_stores.metadata_filters import sanitize_metadata_value  # noqa: PLC0415

    selection_lines = [
        f"- {sanitize_metadata_value(str(field), max_len=80)} = {_render_value(value)}"
        for field, value in list(active_filter.items())[:_MAX_LISTED_FILTERS]
    ]

    parts = [
        "<active_chat_filters>",
        "The user restricted this conversation to:",
        *selection_lines,
        "",
        "These filters are already applied automatically to every document search —",
        "never repeat them inside the query text you send to a search tool.",
    ]

    if has_subagents:
        parts += [
            "",
            "Use this selection to decide which tools to call. Skip the tools it rules",
            "out — calling those wastes a turn and can only return empty or irrelevant",
            "results. Always search the tools the selection still allows before drawing",
            "any conclusion, even when the question sounds like it belongs to an excluded",
            "tool. Only if those searches come back empty should you tell the user that",
            "nothing matches their current filters; never answer from an excluded source.",
        ]

    parts.append("</active_chat_filters>")

    return "\n".join(parts)[:_MAX_BLOCK_LENGTH]


def build_chat_filter_prompt_block(
    agent: Any,
    active_filter: Optional[Dict[str, Any]],
) -> str:
    """Build the ``<active_chat_filters>`` block for *agent*. Never raises.

    Returns ``""`` when no filter is active, so an agent without a selection produces
    a byte-identical system prompt to before this feature existed.

    Pure and synchronous — no DB or vector-store access, so it adds nothing to the
    per-turn latency budget and cannot fail the chat turn.
    """
    if not active_filter:
        return ""

    try:
        has_subagents = bool(getattr(agent, "tool_associations", None))
        block = render_chat_filter_block(active_filter, has_subagents)
        logger.info(
            "chat_filter_scope: announced fields=%s to agent (sub-agents=%s)",
            sorted(active_filter.keys()),
            has_subagents,
        )
        return block
    except Exception:
        logger.warning(
            "chat_filter_scope: could not render the active-filters block — omitted",
            exc_info=True,
        )
        return ""
