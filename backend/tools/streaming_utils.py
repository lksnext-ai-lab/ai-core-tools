"""
SSE (Server-Sent Events) utilities for streaming LangGraph agent responses.

Provides event type constants, formatting helpers, and a mapping function that
translates raw LangGraph astream chunks into our normalized SSE event dicts.

Usage example:
    async for mode, chunk in agent_chain.astream(
        {"messages": messages},
        config=config,
        stream_mode=["messages", "updates", "custom"],
    ):
        events = map_stream_event(mode, chunk)
        if events:
            for event in events:
                yield format_sse_event(event["type"], event["data"])
"""

import json
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# SSE Event Type constants
# ---------------------------------------------------------------------------

#: A partial LLM text output token.
SSE_TOKEN: str = "token"

#: A tool invocation has started.
SSE_TOOL_START: str = "tool_start"

#: A tool invocation has finished.
SSE_TOOL_END: str = "tool_end"

#: A human-readable status message about what the agent is doing.
SSE_THINKING: str = "thinking"

#: Conversation / session metadata (e.g. conversation_id).
SSE_METADATA: str = "metadata"

#: A line of stdout emitted by the sandbox code interpreter in real time.
SSE_CODE_OUTPUT: str = "code_output"

#: An error occurred during streaming.
SSE_ERROR: str = "error"

#: The stream has completed.
SSE_DONE: str = "done"

#: A HumanInTheLoop interrupt is waiting for approval.
SSE_HITL_INTERRUPT: str = "hitl_interrupt"

# ---------------------------------------------------------------------------
# Thinking-message i18n map
# ---------------------------------------------------------------------------

# Keys are stable identifiers — values are the English display strings.
# When i18n support is added, map the keys to the appropriate locale string
# instead of replacing this dict.
_THINKING_MESSAGES: dict[str, str] = {
    "python_repl":              "Running code...",
    "code_interpreter":         "Running code...",
    "web_search":               "Searching the web...",
    "web_search_20250305":      "Searching the web...",
    "google_search":            "Searching the web...",
    "image_generation":         "Generating image...",
    "fetch_file_in_base64":     "Processing file...",
    "download_url_to_workspace":"Downloading file...",
    "skill_loader":             "Loading skill...",
    "load_skill":               "Loading skill...",
}

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def format_sse_event(event_type: str, data: dict) -> str:
    """Serialize a single SSE message line.

    The output follows the HTML Living Standard SSE format::

        data: {"type": "token", "data": {"content": "hello"}}\\n\\n

    Args:
        event_type: One of the ``SSE_*`` constants defined in this module.
        data: Arbitrary payload dict to nest under the ``"data"`` key.

    Returns:
        A fully-formed SSE line ready to be sent to the client.
    """
    payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


def get_thinking_message(tool_name: str, is_agent_tool: bool = False) -> str:
    """Return a human-friendly status message for a given tool name.

    The look-up is case-sensitive and exact for named tools.  Any tool whose
    name contains the substring ``"mcp"`` (case-insensitive) falls back to the
    "Using external tool..." message.  Everything else gets a generic fallback
    that includes the raw tool name.

    Args:
        tool_name: The ``name`` attribute of the tool being invoked.
        is_agent_tool: Pass ``True`` when the tool is an agent-as-tool
            (``IACTTool``).  The caller determines this; this function does
            not attempt to pattern-match agent names.

    Returns:
        A short English status string suitable for display in a chat UI.
    """
    if is_agent_tool:
        return f"Consulting agent {tool_name}..."

    if tool_name in _THINKING_MESSAGES:
        return _THINKING_MESSAGES[tool_name]

    # Dynamic retrieval tools follow the pattern search_{slug}_{silo_id} (AD-8).
    if tool_name.startswith("search_"):
        return "Searching knowledge base..."

    if "mcp" in tool_name.lower():
        return "Using external tool..."

    return f"Using tool {tool_name}..."


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# LangChain agent middleware tags its internal LLM calls via
# `config={"metadata": {"lc_source": "<source>"}}` so downstream consumers can
# tell apart middleware-internal generations (e.g. summaries produced by
# `SummarizationMiddleware`) from the agent's user-facing tokens. We must
# suppress these chunks; otherwise the summary text leaks into the chat
# stream every time the conversation crosses the summarization threshold.
_INTERNAL_LC_SOURCES: frozenset[str] = frozenset({"summarization", "pii"})


def _get_lc_source(metadata: Any) -> str | None:
    """Extract ``lc_source`` from a LangGraph ``messages``-mode metadata dict.

    LangGraph may surface the value either at the top level of the metadata
    dict or nested inside a ``"metadata"`` key, depending on version. Check
    both locations so the filter is resilient across LangGraph upgrades.
    """
    if not isinstance(metadata, dict):
        return None
    direct = metadata.get("lc_source")
    if isinstance(direct, str):
        return direct
    nested = metadata.get("metadata")
    if isinstance(nested, dict):
        nested_source = nested.get("lc_source")
        if isinstance(nested_source, str):
            return nested_source
    return None


def _extract_text_content(content: Any) -> str | None:
    """Safely extract a plain-text string from a message content value.

    LangChain message content can be:
    - A plain string.
    - A list of content blocks (OpenAI multimodal format), each being a dict
      with a ``"type"`` key.  Only ``"text"`` blocks are extracted.

    Returns the concatenated text, or ``None`` if there is nothing to emit.
    """
    if isinstance(content, str):
        return content if content else None

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
        return "".join(parts) if parts else None

    return None


def _map_messages_chunk(chunk: Any) -> list[dict] | None:
    """Handle a single ``messages``-mode chunk from LangGraph astream.

    LangGraph emits chunks for **all** message types (AIMessage, ToolMessage,
    HumanMessage, etc.).  We only want to forward text tokens produced by the
    LLM itself (``AIMessageChunk``), so we explicitly skip every other type.
    This prevents tool call results, echoed user messages, and other non-LLM
    content from leaking into the streaming output.

    Args:
        chunk: A ``(message_chunk, metadata)`` tuple emitted by LangGraph in
            ``stream_mode="messages"`` mode.

    Returns:
        A list containing one ``token`` event dict, or ``None`` to skip.
    """
    if not isinstance(chunk, tuple) or len(chunk) != 2:
        logger.warning(
            "Unexpected messages chunk structure — expected (message_chunk, metadata), "
            "got %s",
            type(chunk).__name__,
        )
        return None

    message_chunk, metadata = chunk

    # Drop tokens generated by middleware-internal LLM calls — these are not
    # part of the agent's reply to the user (e.g. summarization output).
    lc_source = _get_lc_source(metadata)
    if lc_source in _INTERNAL_LC_SOURCES:
        return None

    # Only emit tokens from AI messages — skip ToolMessage, HumanMessage, etc.
    chunk_type = type(message_chunk).__name__
    if chunk_type not in ("AIMessageChunk", "AIMessage"):
        return None

    # Skip chunks that are pure tool-call invocations (no text content)
    tool_calls = getattr(message_chunk, "tool_calls", None) or []
    if tool_calls:
        return None

    content = getattr(message_chunk, "content", None)
    if content is None:
        return None

    text = _extract_text_content(content)
    if not text:
        return None

    return [{"type": SSE_TOKEN, "data": {"content": text}}]


def _map_updates_chunk(chunk: Any) -> list[dict] | None:
    """Handle a single ``updates``-mode chunk from LangGraph astream.

    LangGraph emits ``updates`` as a dict of ``{node_name: state_delta}``.
    We inspect the state delta for:
    - Messages with ``tool_calls`` → emit ``tool_start`` + ``thinking`` events.
    - Messages of type ``ToolMessage`` in a "tools" node → emit ``tool_end``.

    Args:
        chunk: A dict mapping node names to their state delta dicts.

    Returns:
        A list of event dicts, or ``None`` if nothing should be emitted.
    """
    if not isinstance(chunk, dict):
        logger.warning(
            "Unexpected updates chunk — expected dict, got %s",
            type(chunk).__name__,
        )
        return None

    events: list[dict] = []

    for node_name, state_delta in chunk.items():
        if not isinstance(state_delta, dict):
            continue

        messages = state_delta.get("messages", [])
        if not isinstance(messages, list):
            # State delta may store a single message
            messages = [messages]

        for msg in messages:
            if msg is None:
                continue

            # --- tool_start: AI message contains tool_calls ---
            tool_calls = getattr(msg, "tool_calls", None) or []
            for tc in tool_calls:
                try:
                    tool_name: str = (
                        tc.get("name", "") if isinstance(tc, dict)
                        else getattr(tc, "name", "")
                    )
                    tool_call_id: str = (
                        tc.get("id", "") if isinstance(tc, dict)
                        else getattr(tc, "id", "")
                    )
                    tool_args: dict = (
                        tc.get("args", {}) if isinstance(tc, dict)
                        else getattr(tc, "args", {})
                    )
                    if not tool_name:
                        continue

                    # Emit tool_start
                    events.append({
                        "type": SSE_TOOL_START,
                        "data": {
                            "tool_name": tool_name,
                            "tool_call_id": tool_call_id,
                            "args": tool_args,
                            "tool_input": json.dumps(tool_args, ensure_ascii=False) if tool_args else None,
                        },
                    })

                    # Emit thinking status alongside tool_start
                    thinking_msg = get_thinking_message(tool_name)
                    events.append({
                        "type": SSE_THINKING,
                        "data": {"message": thinking_msg, "tool_name": tool_name},
                    })

                except Exception:
                    logger.warning(
                        "Could not extract tool call info from tool_calls entry",
                        exc_info=True,
                    )

            # --- tool_end: ToolMessage in the "tools" node ---
            msg_type = type(msg).__name__
            is_tool_message = msg_type in ("ToolMessage",) or (
                hasattr(msg, "type") and getattr(msg, "type", "") == "tool"
            )
            if is_tool_message and "tool" in node_name.lower():
                try:
                    tool_call_id = getattr(msg, "tool_call_id", "") or ""
                    tool_name_end = getattr(msg, "name", "") or ""
                    raw_output = getattr(msg, "content", None)
                    tool_output: str | None = None
                    if raw_output is not None:
                        tool_output = (
                            raw_output if isinstance(raw_output, str)
                            else json.dumps(raw_output, ensure_ascii=False)
                        )
                    events.append({
                        "type": SSE_TOOL_END,
                        "data": {
                            "tool_name": tool_name_end,
                            "tool_call_id": tool_call_id,
                            "tool_output": tool_output,
                        },
                    })
                except Exception:
                    logger.warning(
                        "Could not extract ToolMessage info for tool_end event",
                        exc_info=True,
                    )

    # --- __interrupt__: HumanInTheLoop middleware paused execution ---
    # Not handled here; the actual interrupt with proper action_requests is
    # detected and emitted in agent_streaming_service.py after checking graph state.

    return events if events else None


def _map_custom_chunk(chunk: Any) -> list[dict] | None:
    """Handle a single ``custom``-mode chunk from LangGraph astream.

    Custom events are arbitrary data emitted by the graph via
    ``dispatch_custom_event``.  Events with ``type == "code_output"`` are
    forwarded as :data:`SSE_CODE_OUTPUT`; everything else becomes a
    ``thinking`` event.

    Args:
        chunk: Arbitrary data emitted as a custom stream event.

    Returns:
        A list containing one event dict.
    """
    if isinstance(chunk, dict) and chunk.get("type") in {
        SSE_TOOL_START,
        SSE_TOOL_END,
        SSE_THINKING,
    }:
        data = chunk.get("data", {})
        if not isinstance(data, dict):
            data = {"message": str(data)}
        return [{"type": chunk["type"], "data": data}]

    if isinstance(chunk, dict) and chunk.get("type") == "code_output":
        stream = chunk.get("stream", "stdout")
        if stream not in ("stdout", "stderr"):
            stream = "stdout"
        data = {
            "line": chunk.get("line", ""),
            "stream": stream,
        }
        for optional_key in (
            "tool_name",
            "parent_tool_name",
            "subagent_name",
            "subagent_id",
        ):
            if chunk.get(optional_key):
                data[optional_key] = chunk.get(optional_key)
        return [
            {
                "type": SSE_CODE_OUTPUT,
                "data": data,
            }
        ]

    if isinstance(chunk, str):
        payload = {"message": chunk}
    elif isinstance(chunk, dict):
        payload = chunk
    else:
        # Convert to string representation as a last resort
        payload = {"message": str(chunk)}

    return [{"type": SSE_THINKING, "data": payload}]


# ---------------------------------------------------------------------------
# Primary public API
# ---------------------------------------------------------------------------


def map_stream_event(mode: str, chunk: Any) -> list[dict] | None:
    """Map a single LangGraph astream event to a list of SSE event dicts.

    Call this inside the ``async for mode, chunk in agent_chain.astream(...)``
    loop.  The function is intentionally defensive — it logs unexpected
    structures and returns ``None`` rather than raising exceptions, so that a
    single malformed event never kills the stream.

    Args:
        mode: The stream mode string, one of ``"messages"``, ``"updates"``, or
            ``"custom"``.  Unknown modes are logged and skipped.
        chunk: The raw chunk emitted by LangGraph for the given mode.

    Returns:
        A list of event dicts (each has ``"type"`` and ``"data"`` keys), or
        ``None`` if the event should be silently discarded.

    Example::

        async for mode, chunk in agent_chain.astream(
            {"messages": messages},
            config=config,
            stream_mode=["messages", "updates", "custom"],
        ):
            events = map_stream_event(mode, chunk)
            if events:
                for event in events:
                    yield format_sse_event(event["type"], event["data"])
    """
    try:
        if mode == "messages":
            return _map_messages_chunk(chunk)

        if mode == "updates":
            return _map_updates_chunk(chunk)

        if mode == "custom":
            return _map_custom_chunk(chunk)

        logger.warning("Unrecognised LangGraph stream mode: %r — skipping", mode)
        return None

    except Exception:
        logger.warning(
            "Unhandled exception while mapping stream event (mode=%r) — skipping",
            mode,
            exc_info=True,
        )
        return None
