"""Unit tests: an error returned by an MCP tool reaches the model instead of aborting the turn.

Regression: the MCP adapter raises ToolException for an ``isError`` result (e.g. a
server rejecting the arguments the model sent), and LangGraph's ToolNode re-raises
it, so the whole chat turn failed instead of letting the model correct the call.
Run with: pytest tests/unit/tools/test_mcp_tool_errors.py -v
"""

import uuid

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool, ToolException

from services.agent_metrics_collector import AgentMetricsCollector
from tools.agentTools import _prepare_mcp_tools

SERVER_ERROR = "1 validation error for call[search]\nq\n  Unexpected keyword argument"


def _mcp_like_tool() -> StructuredTool:
    async def search(**kwargs):
        raise ToolException(SERVER_ERROR)

    return StructuredTool.from_function(
        coroutine=search,
        name="search",
        description="Web search",
        args_schema={
            "type": "object",
            "properties": {"params": {"type": "object", "additionalProperties": True}},
        },
    )


def _call(tool: StructuredTool):
    # How LangGraph's ToolNode runs a model's tool call (see the reported traceback).
    return tool.ainvoke({"type": "tool_call", "name": "search", "args": {"q": "x"}, "id": "call_1"})


@pytest.mark.asyncio
async def test_unprepared_mcp_tool_error_aborts_the_turn():
    """Documents the LangGraph default the fix works around."""
    with pytest.raises(ToolException):
        await _call(_mcp_like_tool())


@pytest.mark.asyncio
async def test_prepared_mcp_tool_error_is_returned_to_the_model():
    tool = _mcp_like_tool()
    _prepare_mcp_tools([tool])

    message = await _call(tool)

    assert isinstance(message, ToolMessage)
    assert message.status == "error"
    assert message.tool_call_id == "call_1"
    assert SERVER_ERROR in message.content
    assert "input schema" in message.content


def test_prepare_mcp_tools_completes_missing_schema_types():
    tool = _mcp_like_tool()
    tool.args_schema["properties"]["mode"] = {"description": "no type"}

    _prepare_mcp_tools([tool])

    assert tool.args_schema["properties"]["mode"]["type"] == "string"


def test_metrics_record_handled_tool_error_as_error():
    collector = AgentMetricsCollector()
    run_id = uuid.uuid4()
    collector.on_tool_start({"name": "search"}, "", run_id=run_id)

    collector.on_tool_end(
        ToolMessage(content="Error: the tool call failed", tool_call_id="call_1", status="error"),
        run_id=run_id,
    )

    (call,) = collector.tool_calls
    assert call["status"] == "ERROR"
    assert call["error_message"].startswith("Error: the tool call failed")


def test_metrics_record_normal_tool_end_as_success():
    collector = AgentMetricsCollector()
    run_id = uuid.uuid4()
    collector.on_tool_start({"name": "search"}, "", run_id=run_id)

    collector.on_tool_end(ToolMessage(content="ok", tool_call_id="call_1"), run_id=run_id)

    (call,) = collector.tool_calls
    assert call["status"] == "SUCCESS"
    assert call["error_message"] is None
