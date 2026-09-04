"""Unit tests for streaming_utils — focuses on the chunk-mapping logic.

The critical regression these tests guard against is the SummarizationMiddleware
leak: middleware-internal LLM calls tag their config with
``{"metadata": {"lc_source": "summarization"}}``, and the streaming layer must
suppress those chunks so the summary text never reaches the SSE token stream.
"""

from unittest.mock import MagicMock

from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage

from tools.streaming_utils import (
    SSE_TOKEN,
    _map_messages_chunk,
    map_stream_event,
)


def _ai_chunk(content: str) -> AIMessageChunk:
    return AIMessageChunk(content=content)


class TestMapMessagesChunk:
    def test_emits_token_for_plain_ai_chunk(self):
        chunk = (_ai_chunk("hello"), {"langgraph_node": "agent"})

        result = _map_messages_chunk(chunk)

        assert result == [{"type": SSE_TOKEN, "data": {"content": "hello"}}]

    def test_drops_summarization_chunk_top_level_metadata(self):
        # SummarizationMiddleware tags its model.ainvoke() with
        # config={"metadata": {"lc_source": "summarization"}}; LangGraph may
        # surface the value at the top level of the metadata dict.
        chunk = (
            _ai_chunk("## SESSION INTENT\nThe user is asking..."),
            {"langgraph_node": "agent", "lc_source": "summarization"},
        )

        assert _map_messages_chunk(chunk) is None

    def test_drops_summarization_chunk_nested_metadata(self):
        # LangGraph also surfaces config metadata under a nested "metadata" key.
        chunk = (
            _ai_chunk("## SUMMARY\n..."),
            {
                "langgraph_node": "agent",
                "metadata": {"lc_source": "summarization"},
            },
        )

        assert _map_messages_chunk(chunk) is None

    def test_unknown_lc_source_is_not_dropped(self):
        # Only known internal sources are filtered; unknown values pass through
        # so that a future, unrelated `lc_source` does not silently break the stream.
        chunk = (
            _ai_chunk("regular reply"),
            {"langgraph_node": "agent", "lc_source": "user_facing_thing"},
        )

        result = _map_messages_chunk(chunk)

        assert result == [{"type": SSE_TOKEN, "data": {"content": "regular reply"}}]

    def test_skips_tool_message(self):
        msg = ToolMessage(content="result", tool_call_id="abc")
        chunk = (msg, {"langgraph_node": "tools"})

        assert _map_messages_chunk(chunk) is None

    def test_skips_human_message(self):
        msg = HumanMessage(content="hi")
        chunk = (msg, {"langgraph_node": "agent"})

        assert _map_messages_chunk(chunk) is None

    def test_skips_pure_tool_call_chunk(self):
        ai = MagicMock()
        ai.__class__.__name__ = "AIMessageChunk"
        ai.tool_calls = [{"name": "search", "id": "1", "args": {}}]
        ai.content = ""

        # Patch isinstance check by routing through the public dispatcher.
        # Direct unit on _map_messages_chunk uses type().__name__, so a real
        # AIMessageChunk wrapper is more faithful here.
        chunk_obj = AIMessageChunk(
            content="",
            tool_call_chunks=[{"name": "search", "id": "1", "args": "{}", "index": 0}],
        )
        chunk = (chunk_obj, {"langgraph_node": "agent"})

        assert _map_messages_chunk(chunk) is None

    def test_skips_empty_content(self):
        chunk = (_ai_chunk(""), {"langgraph_node": "agent"})

        assert _map_messages_chunk(chunk) is None

    def test_handles_malformed_chunk(self):
        assert _map_messages_chunk("not a tuple") is None
        assert _map_messages_chunk((_ai_chunk("x"),)) is None

    def test_handles_missing_metadata(self):
        # If metadata is None or non-dict, the filter must still pass through
        # legitimate tokens rather than crashing.
        chunk = (_ai_chunk("ok"), None)

        result = _map_messages_chunk(chunk)

        assert result == [{"type": SSE_TOKEN, "data": {"content": "ok"}}]


class TestMapStreamEventDispatcher:
    def test_messages_mode_routes_to_messages_handler(self):
        chunk = (_ai_chunk("hi"), {"langgraph_node": "agent"})

        events = map_stream_event("messages", chunk)

        assert events == [{"type": SSE_TOKEN, "data": {"content": "hi"}}]

    def test_messages_mode_drops_summarization(self):
        chunk = (
            _ai_chunk("## SESSION INTENT\nleak"),
            {"metadata": {"lc_source": "summarization"}},
        )

        assert map_stream_event("messages", chunk) is None
from backend.tools.streaming_utils import SSE_CODE_OUTPUT, SSE_TOOL_START, map_stream_event


def test_code_output_custom_event_preserves_stream():
    events = map_stream_event(
        "custom",
        {"type": "code_output", "stream": "stderr", "line": "warn\n"},
    )

    assert events == [
        {
            "type": SSE_CODE_OUTPUT,
            "data": {"line": "warn\n", "stream": "stderr"},
        }
    ]


def test_code_output_custom_event_defaults_unknown_stream_to_stdout():
    events = map_stream_event(
        "custom",
        {"type": "code_output", "stream": "invalid", "line": "hello\n"},
    )

    assert events == [
        {
            "type": SSE_CODE_OUTPUT,
            "data": {"line": "hello\n", "stream": "stdout"},
        }
    ]


def test_code_output_custom_event_preserves_tool_name():
    events = map_stream_event(
        "custom",
        {
            "type": "code_output",
            "tool_name": "python_repl",
            "stream": "stdout",
            "line": "hello\n",
        },
    )

    assert events == [
        {
            "type": SSE_CODE_OUTPUT,
            "data": {
                "tool_name": "python_repl",
                "line": "hello\n",
                "stream": "stdout",
            },
        }
    ]


def test_custom_tool_event_is_forwarded():
    events = map_stream_event(
        "custom",
        {
            "type": "tool_start",
            "data": {
                "tool_name": "python_repl",
                "tool_call_id": "subagent:call-1",
                "subagent_name": "Research Agent",
            },
        },
    )

    assert events == [
        {
            "type": SSE_TOOL_START,
            "data": {
                "tool_name": "python_repl",
                "tool_call_id": "subagent:call-1",
                "subagent_name": "Research Agent",
            },
        }
    ]


def test_code_output_custom_event_preserves_subagent_context():
    events = map_stream_event(
        "custom",
        {
            "type": "code_output",
            "tool_name": "python_repl",
            "parent_tool_name": "Research_Agent",
            "subagent_name": "Research Agent",
            "subagent_id": 42,
            "stream": "stdout",
            "line": "hello\n",
        },
    )

    assert events == [
        {
            "type": SSE_CODE_OUTPUT,
            "data": {
                "tool_name": "python_repl",
                "parent_tool_name": "Research_Agent",
                "subagent_name": "Research Agent",
                "subagent_id": 42,
                "line": "hello\n",
                "stream": "stdout",
            },
        }
    ]
