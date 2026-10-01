"""Unit tests for ``tools.agentTools.IACTTool`` (agent-as-tool wrapper).

Focus: the async factory ``IACTTool.create`` must load the sub-agent's MCP tools
(the bug being fixed), and must keep working when the MCP server fails. Also
covers the orchestrator-level metadata dropdown filter whitelisting (Gate 1 in
``create_agent``, Gate 2 in ``_resolve_and_build_retriever_tool``).

All external dependencies are mocked — no LLM, MCP server or database is touched.
"""

import json
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from models.agent import Agent, AgentTool
from models.ocr_agent import OCRAgent
from models.silo import Silo
from tools import agentTools


def _make_agent(name: str = "Sub Agent") -> Agent:
    """Build a transient (un-persisted) Agent suitable for IACTTool construction."""
    return Agent(name=name, description=f"{name} description", system_prompt="")


def _make_orchestrator(exposed_chat_filters=None, tool_agents=None) -> Agent:
    """Build a transient orchestrator Agent wired to *tool_agents* via ``tool_associations``.

    ``tool_associations`` is a relationship collection; on a transient (never
    session-attached) object it can be assigned directly without touching the DB.
    """
    orchestrator = Agent(
        name="Orchestrator",
        description="Orchestrator description",
        system_prompt="",
        output_parser_id=None,
        silo_id=None,
        has_memory=False,
        enable_code_interpreter=False,
    )
    orchestrator.exposed_chat_filters = exposed_chat_filters or []
    associations = []
    for tool_agent in (tool_agents or []):
        assoc = AgentTool()
        assoc.tool = tool_agent
        associations.append(assoc)
    orchestrator.tool_associations = associations
    return orchestrator


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


# ---------------------------------------------------------------------------
# Gate 1 — orchestrator-level whitelist, applied in create_agent()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_agent_gate1_whitelists_caller_filter_by_exposed_fields():
    """Only fields listed in ``exposed_chat_filters`` reach ``IACTTool.create``.

    A caller filter with an approved field (``machine_model``) and an
    unapproved one (``not_exposed``) must have the unapproved field dropped
    before it is ever forwarded to a sub-agent.
    """
    sub_agent = _make_agent("Sub Agent")
    orchestrator = _make_orchestrator(
        exposed_chat_filters=["machine_model"], tool_agents=[sub_agent]
    )

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()),
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch.object(
            agentTools.IACTTool, "create", new=AsyncMock(return_value=MagicMock())
        ) as mock_iact_create,
    ):
        await agentTools.create_agent(
            orchestrator,
            search_params={"filter": {"machine_model": "X100", "not_exposed": "foo"}},
        )

    mock_iact_create.assert_awaited_once()
    call = mock_iact_create.await_args
    assert call.args[0] is sub_agent
    assert call.kwargs["caller_filter"] == {"machine_model": "X100"}


@pytest.mark.asyncio
async def test_create_agent_gate1_drops_field_absent_from_exposed_chat_filters():
    """A field not listed in ``exposed_chat_filters`` never reaches ``IACTTool.create``,
    independent of whether any sub-agent's silo would otherwise declare it (Gate 2)."""
    sub_agent = _make_agent("Sub Agent")
    orchestrator = _make_orchestrator(exposed_chat_filters=[], tool_agents=[sub_agent])

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()),
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch.object(
            agentTools.IACTTool, "create", new=AsyncMock(return_value=MagicMock())
        ) as mock_iact_create,
    ):
        await agentTools.create_agent(
            orchestrator,
            search_params={"filter": {"machine_model": "X100"}},
        )

    mock_iact_create.assert_awaited_once()
    assert mock_iact_create.await_args.kwargs["caller_filter"] == {}


@pytest.mark.asyncio
async def test_create_agent_gate1_empty_exposed_chat_filters_is_never_null():
    """``exposed_chat_filters`` unset (None on a transient agent) degrades to an
    empty whitelist, not a crash — orchestrator_caller_filter is always a dict."""
    sub_agent = _make_agent("Sub Agent")
    orchestrator = _make_orchestrator(exposed_chat_filters=None, tool_agents=[sub_agent])
    orchestrator.exposed_chat_filters = None  # simulate an un-flushed column default

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()),
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch.object(
            agentTools.IACTTool, "create", new=AsyncMock(return_value=MagicMock())
        ) as mock_iact_create,
    ):
        await agentTools.create_agent(
            orchestrator,
            search_params={"filter": {"machine_model": "X100"}},
        )

    assert mock_iact_create.await_args.kwargs["caller_filter"] == {}


# ---------------------------------------------------------------------------
# Gate 2 — per-subagent silo whitelist, applied in
# _resolve_and_build_retriever_tool (reached via IACTTool.create)
# ---------------------------------------------------------------------------


def _make_silo_stub(fields: list, vector_db_type: str = "PGVECTOR") -> Silo:
    """Build a transient (un-persisted) Silo with a fake metadata_definition.

    Must be a real ``Silo`` ORM instance (not a bare SimpleNamespace): assigning
    to ``Agent.silo`` fires a back_populates backref event that requires the
    assigned object to carry SQLAlchemy instance state. ``metadata_definition``
    itself has no back_populates, so a plain SimpleNamespace duck-type works
    fine there (mirrors the ``test_resolve_search_params.py`` convention).
    """
    silo = Silo(vector_db_type=vector_db_type)
    silo.metadata_definition = types.SimpleNamespace(fields=fields)
    return silo


@pytest.mark.asyncio
async def test_iact_tool_create_gate2_forwards_filter_when_silo_declares_field():
    """A caller_filter field declared by the sub-agent's own silo reaches
    ``resolve_search_params`` scoped down to a flat {field: value} filter dict."""
    agent = _make_agent("RAG Sub-Agent")
    agent.silo_id = 99
    agent.silo = _make_silo_stub(fields=[{"name": "machine_model", "type": "str"}])
    agent.rag_max_retrieval_calls = 3

    resolved_sp = {"k": 7}
    resolved_pinned = {"machine_model": {"$eq": "X100"}}
    sentinel_tool = MagicMock()

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()),
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch(
            "services.silo_service.resolve_search_params",
            return_value=(resolved_sp, resolved_pinned),
        ) as mock_resolve,
        patch("tools.agentTools.get_retriever_tool", return_value=sentinel_tool),
    ):
        await agentTools.IACTTool.create(agent, caller_filter={"machine_model": "X100"})

    assert mock_resolve.call_args.args[0] is agent
    assert mock_resolve.call_args.args[1] == {"filter": {"machine_model": "X100"}}


@pytest.mark.asyncio
async def test_iact_tool_create_gate2_drops_filter_when_silo_does_not_declare_field():
    """A caller_filter field NOT declared by this sub-agent's silo is dropped for
    this sub-agent only (Gate 2) — resolve_search_params receives no filter."""
    agent = _make_agent("RAG Sub-Agent")
    agent.silo_id = 99
    # This silo's metadata schema declares a *different* field only.
    agent.silo = _make_silo_stub(fields=[{"name": "other_field", "type": "str"}])
    agent.rag_max_retrieval_calls = 3

    resolved_sp = {"k": 7}
    resolved_pinned = {}
    sentinel_tool = MagicMock()

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()),
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch(
            "services.silo_service.resolve_search_params",
            return_value=(resolved_sp, resolved_pinned),
        ) as mock_resolve,
        patch("tools.agentTools.get_retriever_tool", return_value=sentinel_tool),
    ):
        await agentTools.IACTTool.create(agent, caller_filter={"machine_model": "X100"})

    assert mock_resolve.call_args.args[0] is agent
    # The whole caller_search_params collapses to None: scoped_filter was empty.
    assert mock_resolve.call_args.args[1] is None


@pytest.mark.asyncio
async def test_iact_tool_create_no_caller_filter_never_touches_silo_or_scoping():
    """caller_filter=None (default) is the existing, unchanged path: no scoping
    work is attempted and resolve_search_params gets None, matching the
    pre-existing ``test_iact_tool_create_uses_sub_agent_rag_config`` behavior."""
    agent = _make_agent("RAG Sub-Agent")
    agent.silo_id = 99
    agent.rag_max_retrieval_calls = 3

    resolved_sp = {"k": 7}
    resolved_pinned = {}
    sentinel_tool = MagicMock()

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()),
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch(
            "services.silo_service.resolve_search_params",
            return_value=(resolved_sp, resolved_pinned),
        ) as mock_resolve,
        patch("tools.agentTools.get_retriever_tool", return_value=sentinel_tool),
    ):
        await agentTools.IACTTool.create(agent)

    assert mock_resolve.call_args.args[1] is None


# ---------------------------------------------------------------------------
# Nested tool-agents — caller_filter forwarded unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_iact_tool_create_forwards_caller_filter_to_nested_tool_agents():
    """A nested sub-agent-of-a-sub-agent receives the same already-whitelisted
    caller_filter unchanged — no re-derivation against a nested exposed_chat_filters.

    Uses the real (unmocked) recursive ``IACTTool.create`` call and verifies the
    filter reached the grandchild's own Gate 2 scoping via ``resolve_search_params``.
    """
    grandchild = _make_agent("Grandchild")
    grandchild.silo_id = 99
    grandchild.silo = _make_silo_stub(fields=[{"name": "machine_model", "type": "str"}])

    child = _make_agent("Child")
    child.silo_id = None  # no retriever of its own — just wraps the grandchild
    assoc = AgentTool()
    assoc.tool = grandchild
    child.tool_associations = [assoc]

    resolved_sp = {"k": 7}
    resolved_pinned = {"machine_model": {"$eq": "X100"}}

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()),
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch(
            "services.silo_service.resolve_search_params",
            return_value=(resolved_sp, resolved_pinned),
        ) as mock_resolve,
        patch("tools.agentTools.get_retriever_tool", return_value=MagicMock()),
    ):
        await agentTools.IACTTool.create(child, caller_filter={"machine_model": "X100"})

    # resolve_search_params was reached for the grandchild with the filter intact.
    mock_resolve.assert_called_once()
    assert mock_resolve.call_args.args[0] is grandchild
    assert mock_resolve.call_args.args[1] == {"filter": {"machine_model": "X100"}}


# ---------------------------------------------------------------------------
# <active_chat_filters> prompt injection (create_agent)
#
# Soft approach: the orchestrator is TOLD which sub-agent tools can match the
# user's filter selection, but every sub-agent tool is still built and callable.
# ---------------------------------------------------------------------------

_SENTINEL_BLOCK = "<active_chat_filters>\nSENTINEL\n</active_chat_filters>"


@pytest.mark.asyncio
async def test_create_agent_injects_filter_block_and_keeps_all_tools():
    """The block reaches the orchestrator's system prompt, and — this is the whole
    point of the soft approach — no sub-agent tool is dropped because of it."""
    sub_a = _make_agent("Sub A")
    sub_b = _make_agent("Sub B")
    orchestrator = _make_orchestrator(
        exposed_chat_filters=["source_type"], tool_agents=[sub_a, sub_b]
    )

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()) as mock_create,
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch.object(agentTools.IACTTool, "create", new=AsyncMock(return_value=MagicMock())),
        patch(
            "tools.agentTools.build_chat_filter_prompt_block",
            return_value=_SENTINEL_BLOCK,
        ) as mock_block,
    ):
        await agentTools.create_agent(
            orchestrator, search_params={"filter": {"source_type": "SAT"}}
        )

    mock_block.assert_called_once()
    assert mock_block.call_args.args[1] == {"source_type": "SAT"}

    kwargs = mock_create.call_args.kwargs
    assert _SENTINEL_BLOCK in kwargs["system_prompt"]
    assert len(kwargs["tools"]) == 2  # both sub-agents still offered to the model


@pytest.mark.asyncio
async def test_create_agent_no_search_params_leaves_prompt_untouched():
    """Zero behaviour change when the user selected nothing."""
    orchestrator = _make_orchestrator(
        exposed_chat_filters=["source_type"], tool_agents=[_make_agent("Sub A")]
    )

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()) as mock_create,
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch.object(agentTools.IACTTool, "create", new=AsyncMock(return_value=MagicMock())),
    ):
        await agentTools.create_agent(orchestrator, search_params=None)

    assert "<active_chat_filters>" not in mock_create.call_args.kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_create_agent_no_exposed_chat_filters_leaves_prompt_untouched():
    """Gate 1 empties the filter, so there is nothing to announce."""
    orchestrator = _make_orchestrator(
        exposed_chat_filters=[], tool_agents=[_make_agent("Sub A")]
    )

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()) as mock_create,
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch.object(agentTools.IACTTool, "create", new=AsyncMock(return_value=MagicMock())),
    ):
        await agentTools.create_agent(
            orchestrator, search_params={"filter": {"source_type": "SAT"}}
        )

    assert "<active_chat_filters>" not in mock_create.call_args.kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_create_agent_survives_filter_block_failure():
    """A failure building the block must degrade the prompt, never the chat turn."""
    orchestrator = _make_orchestrator(
        exposed_chat_filters=["source_type"], tool_agents=[_make_agent("Sub A")]
    )

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()) as mock_create,
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch.object(agentTools.IACTTool, "create", new=AsyncMock(return_value=MagicMock())),
        patch(
            "tools.chat_filter_scope.render_chat_filter_block",
            side_effect=RuntimeError("boom"),
        ),
    ):
        await agentTools.create_agent(
            orchestrator, search_params={"filter": {"source_type": "SAT"}}
        )

    # Agent still built; the block is simply absent.
    assert "<active_chat_filters>" not in mock_create.call_args.kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_filter_block_precedes_output_format_instructions():
    """<output_format_instructions> must stay the last block in the prompt."""
    orchestrator = _make_orchestrator(
        exposed_chat_filters=["source_type"], tool_agents=[_make_agent("Sub A")]
    )
    orchestrator.output_parser_id = 7

    parser = MagicMock()
    parser.get_format_instructions.return_value = "FORMAT_RULES"

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.get_output_parser", return_value=parser),
        patch("tools.agentTools.get_parser_model_by_id", return_value=None),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()) as mock_create,
        patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)),
        patch.object(agentTools.IACTTool, "create", new=AsyncMock(return_value=MagicMock())),
        patch(
            "tools.agentTools.build_chat_filter_prompt_block",
            return_value=_SENTINEL_BLOCK,
        ),
    ):
        await agentTools.create_agent(
            orchestrator, search_params={"filter": {"source_type": "SAT"}}
        )

    prompt = mock_create.call_args.kwargs["system_prompt"]
    assert prompt.index("<active_chat_filters>") < prompt.index("<output_format_instructions>")


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


# === OCR Agent-as-tool tests ===


def _make_ocr_agent(name: str = "OCR Tool") -> OCRAgent:
    """Build a transient (un-persisted) OCRAgent suitable for IACTOCRTool construction."""
    ocr = OCRAgent(name=name, description=f"{name} description", system_prompt="")
    ocr.type = "ocr_agent"
    return ocr


@pytest.mark.asyncio
async def test_iact_ocr_tool_detects_ocr_agent():
    """discover_tool should return IACTOCRTool when given an OCRAgent."""
    ocr_agent = _make_ocr_agent()

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()),
        patch.object(
            agentTools.MCPClientManager,
            "get_client",
            new=AsyncMock(return_value=None),
        ),
    ):
        tool_instance = await agentTools.discover_tool(
            ocr_agent,
            user_context=None,
        )

    assert isinstance(tool_instance, agentTools.IACTOCRTool)


@pytest.mark.asyncio
async def test_iact_ocr_tool_falls_back_to_chat_when_no_files():
    """IACTOCRTool should delegate to chat agents when no PDF file was provided."""
    ocr_agent = _make_ocr_agent()

    fake_react = MagicMock()
    fake_react.ainvoke = AsyncMock(
        return_value={
            "messages": [
                MagicMock(content="plain chat response")
            ]
        }
    )

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch(
            "tools.agentTools.create_langchain_agent",
            return_value=fake_react,
        ),
        patch.object(
            agentTools.MCPClientManager,
            "get_client",
            new=AsyncMock(return_value=None),
        ),
    ):
        tool_instance = await agentTools.IACTOCRTool.create(ocr_agent)

    result = await tool_instance._arun(query="hello")

    assert result == "plain chat response"


@pytest.mark.asyncio
async def test_iact_ocr_tool_uses_attached_pdf_files():
    ocr_agent = _make_ocr_agent()

    attached_files = [
        {
            "filename": "invoice.pdf",
            "type": "pdf",
            "file_path": "/tmp/invoice.pdf",
        }
    ]

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch(
            "tools.agentTools._execute_tool_agent_ocr",
            new=AsyncMock(return_value={"amount": 100}),
        ) as mock_exec,
        patch(
            "tools.agentTools.create_langchain_agent",
            return_value=MagicMock(),
        ),
        patch.object(
            agentTools.MCPClientManager,
            "get_client",
            new=AsyncMock(return_value=None),
        ),
        patch("os.path.exists", return_value=True),
    ):
        tool = await agentTools.IACTOCRTool.create(
            ocr_agent,
            attached_files=attached_files,
        )

        result = await tool._arun(query="extract")

    mock_exec.assert_awaited_once()
    # Regression: the already-unwrapped OCR content must reach the parent
    # agent instead of being unwrapped a second time into null.
    assert json.loads(result) == [{"file": "invoice.pdf", "content": {"amount": 100}}]


@pytest.mark.asyncio
async def test_iact_ocr_tool_reports_missing_pdf():
    ocr_agent = _make_ocr_agent()

    attached_files = [
        {
            "filename": "missing.pdf",
            "type": "pdf",
            "file_path": "/tmp/missing.pdf",
        }
    ]

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch(
            "tools.agentTools.create_langchain_agent",
            return_value=MagicMock(),
        ),
        patch.object(
            agentTools.MCPClientManager,
            "get_client",
            new=AsyncMock(return_value=None),
        ),
        patch("os.path.exists", return_value=False),
    ):
        tool = await agentTools.IACTOCRTool.create(
            ocr_agent,
            attached_files=attached_files,
        )

        result = await tool._arun(query="extract")

    assert "PDF file not found" in result


@pytest.mark.asyncio
async def test_iact_ocr_tool_processes_multiple_pdfs():
    ocr_agent = _make_ocr_agent()

    attached_files = [
        {
            "filename": "a.pdf",
            "type": "pdf",
            "file_path": "/tmp/a.pdf",
        },
        {
            "filename": "b.pdf",
            "type": "pdf",
            "file_path": "/tmp/b.pdf",
        },
    ]

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch(
            "tools.agentTools._execute_tool_agent_ocr",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_exec,
        patch(
            "tools.agentTools.create_langchain_agent",
            return_value=MagicMock(),
        ),
        patch.object(
            agentTools.MCPClientManager,
            "get_client",
            new=AsyncMock(return_value=None),
        ),
        patch("os.path.exists", return_value=True),
    ):
        tool = await agentTools.IACTOCRTool.create(
            ocr_agent,
            attached_files=attached_files,
        )

        await tool._arun(query="extract")

    assert mock_exec.await_count == 2
