"""Unit tests for AgentMetricsCollector using real LangChain runs (fake chat models).

Checks what the collector attributes to the agent itself: its direct LLM calls
and tool calls — never the calls a sub-agent makes inside an AGENT tool.
"""
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from services.agent_metrics_collector import (
    METRICS_SUB_AGENT_ID_KEY,
    METRICS_TOOL_TYPE_KEY,
    AgentMetricsCollector,
)


def _llm(inp: int, out: int, model: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(
        content="ok",
        usage_metadata={"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out},
        response_metadata={"model_name": model},
    )]))


def _tool(name, coroutine, tool_type=None, **metadata):
    if tool_type:
        metadata[METRICS_TOOL_TYPE_KEY] = tool_type
    return StructuredTool.from_function(coroutine=coroutine, name=name, description=name, metadata=metadata or None)


@pytest.mark.asyncio
async def test_counts_direct_llm_calls_and_sums_usage():
    collector = AgentMetricsCollector()
    config = {"callbacks": [collector]}

    await _llm(100, 20, "gpt-5-mini").ainvoke("a", config=config)
    await _llm(50, 10, "gpt-5-mini").ainvoke("b", config=config)

    assert collector.llm_calls == 2
    assert collector.token_usage() == (150, 30, 180)
    assert collector.model_name == "gpt-5-mini"


@pytest.mark.asyncio
async def test_records_tool_type_duration_and_errors():
    collector = AgentMetricsCollector()
    config = {"callbacks": [collector]}

    async def search(q: str) -> str:
        return "docs"

    async def broken(q: str) -> str:
        raise RuntimeError("mcp server down")

    await _tool("retrieve", search, "RETRIEVER").ainvoke({"q": "x"}, config=config)
    with pytest.raises(RuntimeError):
        await _tool("remote_lookup", broken, "MCP").ainvoke({"q": "x"}, config=config)
    await _tool("untagged_helper", search).ainvoke({"q": "x"}, config=config)

    calls = {c["tool_name"]: c for c in collector.tool_calls}
    assert calls["retrieve"]["tool_type"] == "RETRIEVER"
    assert calls["retrieve"]["status"] == "SUCCESS"
    assert calls["retrieve"]["duration_ms"] >= 0
    assert calls["remote_lookup"]["status"] == "ERROR"
    assert "mcp server down" in calls["remote_lookup"]["error_message"]
    assert calls["untagged_helper"]["tool_type"] == "BUILTIN"


@pytest.mark.asyncio
async def test_excludes_calls_made_inside_a_sub_agent():
    collector = AgentMetricsCollector()
    config = {"callbacks": [collector]}
    inner_llm = _llm(1000, 1000, "sub-model")

    async def inner(q: str) -> str:
        return "inner"

    inner_tool = _tool("inner_tool", inner, "BUILTIN")

    async def sub_agent(q: str) -> str:
        # Like IACTTool: nested runs are invoked without passing config.
        await inner_llm.ainvoke(q)
        await inner_tool.ainvoke({"q": q})
        return "sub-agent answer"

    await _llm(10, 5, "root-model").ainvoke("root", config=config)
    await _tool("helper_agent", sub_agent, "AGENT", **{METRICS_SUB_AGENT_ID_KEY: 42}).ainvoke(
        {"q": "delegate"}, config=config
    )

    assert collector.llm_calls == 1
    assert collector.token_usage() == (10, 5, 15)
    assert collector.model_name == "root-model"
    assert [c["tool_name"] for c in collector.tool_calls] == ["helper_agent"]
    assert collector.tool_calls[0]["sub_agent_id"] == 42


def test_no_usage_reported_yields_none():
    assert AgentMetricsCollector().token_usage() == (None, None, None)
