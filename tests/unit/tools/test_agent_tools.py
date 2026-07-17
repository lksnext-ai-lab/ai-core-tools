"""Unit tests for ``tools.agentTools.IACTTool`` (agent-as-tool wrapper).

Focus: the async factory ``IACTTool.create`` must load the sub-agent's MCP tools
(the bug being fixed), and must keep working when the MCP server fails.

All external dependencies are mocked — no LLM, MCP server or database is touched.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from models.agent import Agent
from tools import agentTools


def _make_agent(name: str = "Sub Agent") -> Agent:
    """Build a transient (un-persisted) Agent suitable for IACTTool construction."""
    return Agent(name=name, description=f"{name} description", system_prompt="")


class _StreamingReactAgent:
    async def astream(self, _payload, stream_mode=None):
        assert stream_mode == ["updates", "custom"]
        yield (
            "updates",
            {
                "agent": {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "python_repl",
                                    "id": "call-1",
                                    "args": {"code": "print('hi')"},
                                }
                            ],
                        )
                    ]
                }
            },
        )
        yield (
            "custom",
            {
                "type": "code_output",
                "tool_name": "python_repl",
                "stream": "stdout",
                "line": "hi\n",
            },
        )
        yield (
            "updates",
            {
                "tools": {
                    "messages": [
                        ToolMessage(
                            content="hi\n",
                            name="python_repl",
                            tool_call_id="call-1",
                        )
                    ]
                }
            },
        )
        yield (
            "updates",
            {
                "agent": {
                    "messages": [AIMessage(content="Sub-agent final answer")]
                }
            },
        )

    async def ainvoke(self, _payload):
        raise AssertionError("ainvoke should not be used when a stream writer is available")


@pytest.mark.asyncio
async def test_iact_tool_create_builds_react_agent():
    """The async factory returns a ready IACTTool with its react_agent built."""
    agent = _make_agent()

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()),
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
    ):
        tool = await agentTools.IACTTool.create(agent)

    assert isinstance(tool, agentTools.IACTTool)
    assert tool.react_agent is not None


@pytest.mark.asyncio
async def test_iact_tool_create_loads_sub_agent_mcp_tools():
    """A sub-agent's MCP tools are loaded and added to its react_agent."""
    agent = _make_agent("MCP Sub-Agent")

    fake_mcp_tool = MagicMock()
    fake_client = MagicMock()
    fake_client.get_tools = AsyncMock(return_value=[fake_mcp_tool])

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()) as mock_create,
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=fake_client)),
    ):
        tool = await agentTools.IACTTool.create(agent, user_context={"user_id": 1})

    loaded_tools = mock_create.call_args.kwargs["tools"]
    assert fake_mcp_tool in loaded_tools
    # The MCP client is kept on the instance so its connection lives as long as the tool.
    assert tool.mcp_client is fake_client


@pytest.mark.asyncio
async def test_iact_tool_create_survives_mcp_load_failure():
    """A failing MCP server degrades the sub-agent but never breaks construction."""
    agent = _make_agent("MCP Sub-Agent")

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()) as mock_create,
        patch.object(
            agentTools.MCPClientManager,
            "get_client",
            new=AsyncMock(side_effect=RuntimeError("MCP server down")),
        ),
    ):
        tool = await agentTools.IACTTool.create(agent)

    assert tool.react_agent is not None
    assert tool.mcp_client is None
    # Base tools are still present despite the MCP failure.
    assert agentTools.fetch_file_in_base64 in mock_create.call_args.kwargs["tools"]


@pytest.mark.asyncio
async def test_iact_tool_create_uses_sub_agent_rag_config():
    """AC-17: the sub-agent retriever is built from the sub-agent's OWN RAG config.

    ``get_retriever_tool`` must receive the params resolved for THIS agent plus its
    own ``rag_max_retrieval_calls`` — not the root agent's caller params.
    """
    agent = _make_agent("RAG Sub-Agent")
    agent.silo_id = 99
    agent.rag_max_retrieval_calls = 3

    resolved_sp = {"k": 7, "search_type": "mmr"}
    resolved_pinned = {"anio": {"$eq": 2024}}
    sentinel_tool = MagicMock()

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()) as mock_create,
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch(
            "services.silo_service.resolve_search_params",
            return_value=(resolved_sp, resolved_pinned),
        ) as mock_resolve,
        patch("tools.agentTools.get_retriever_tool", return_value=sentinel_tool) as mock_get_ret,
    ):
        await agentTools.IACTTool.create(agent)

    # Precedence is resolved for the sub-agent itself, with NO caller search params.
    assert mock_resolve.call_args.args[0] is agent
    assert mock_resolve.call_args.args[1] is None

    # The dynamic tool is built with the resolved params + the sub-agent's own ceiling.
    ret_args = mock_get_ret.call_args.args
    assert ret_args[0] is agent.silo
    assert ret_args[1] == resolved_sp
    assert ret_args[2] == 3
    assert ret_args[3] == resolved_pinned

    # The retriever tool is wired into the sub-agent's toolset.
    assert sentinel_tool in mock_create.call_args.kwargs["tools"]


@pytest.mark.asyncio
async def test_iact_tool_create_skips_retriever_without_silo():
    """A sub-agent without a silo builds no retriever tool and never resolves params."""
    agent = _make_agent("No-Silo Sub-Agent")
    agent.silo_id = None

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()),
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch("services.silo_service.resolve_search_params") as mock_resolve,
        patch("tools.agentTools.get_retriever_tool") as mock_get_ret,
    ):
        await agentTools.IACTTool.create(agent)

    mock_resolve.assert_not_called()
    mock_get_ret.assert_not_called()


@pytest.mark.asyncio
async def test_iact_tool_create_adds_shared_sandbox_tools(tmp_path):
    """Agent-tools with code interpreter reuse the parent sandbox handle."""
    agent = _make_agent("Sandbox Sub-Agent")
    agent.enable_code_interpreter = True

    handle = MagicMock()
    handle.sandbox_id = "parent-sandbox"
    handle.provider_name = "opensandbox"
    provider = MagicMock()
    provider.get_supported_languages.return_value = ["python"]
    session_service = MagicMock()
    repl_tool = MagicMock()
    repl_tool.name = "python_repl"

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()) as mock_create,
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch("tools.agentTools.create_sandbox_repl_tools", return_value=[repl_tool]) as make_repl_tools,
    ):
        await agentTools.IACTTool.create(
            agent,
            user_context={"user_id": 1},
            working_dir=str(tmp_path),
            sandbox_handle=handle,
            sandbox_provider=provider,
            sandbox_session_key="conv_1_99",
            sandbox_session_service=session_service,
        )

    make_repl_tools.assert_called_once_with(
        handle,
        provider,
        session_key="conv_1_99",
        session_service=session_service,
    )
    assert repl_tool in mock_create.call_args.kwargs["tools"]
    assert "same sandbox used by the parent agent" in mock_create.call_args.kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_iact_tool_arun_forwards_subagent_tool_events():
    agent = _make_agent("Research Agent")
    agent.agent_id = 42
    emitted_events = []

    with patch("tools.agentTools.get_llm", return_value=object()):
        tool = agentTools.IACTTool(agent)
    tool.react_agent = _StreamingReactAgent()

    with patch("langgraph.config.get_stream_writer", return_value=emitted_events.append):
        result = await tool._arun("run code")

    assert result == "Sub-agent final answer"
    assert emitted_events[0] == {
        "type": "tool_start",
        "data": {
            "tool_name": "python_repl",
            "tool_call_id": "Research_Agent:42:call-1",
            "args": {"code": "print('hi')"},
            "tool_input": '{"code": "print(\'hi\')"}',
            "parent_tool_name": "Research_Agent",
            "subagent_name": "Research Agent",
            "subagent_id": 42,
            "raw_tool_call_id": "call-1",
        },
    }
    assert emitted_events[2] == {
        "type": "code_output",
        "tool_name": "python_repl",
        "stream": "stdout",
        "line": "hi\n",
        "parent_tool_name": "Research_Agent",
        "subagent_name": "Research Agent",
        "subagent_id": 42,
    }
    assert emitted_events[3]["type"] == "tool_end"
    assert emitted_events[3]["data"]["tool_call_id"] == "Research_Agent:42:call-1"
