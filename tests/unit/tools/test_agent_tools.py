from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.a2a_agent import A2AAgent
from models.agent import Agent, AgentTool
from services.a2a_executor_service import A2AExecutionResult
from tools import agentTools


def _make_agent(name: str, *, prompt_template: str | None = None, a2a: bool = False) -> Agent:
    agent = Agent(
        name=name,
        description=f"{name} description",
        system_prompt="",
        prompt_template=prompt_template,
    )
    if a2a:
        agent.a2a_config = A2AAgent(
            card_url="https://example.com/.well-known/agent-card.json",
            remote_agent_id="https://example.com",
            remote_agent_metadata={},
        )
    return agent


def test_build_agent_tool_returns_a2a_wrapper_for_imported_agent():
    remote_agent = _make_agent("Say Hello", a2a=True)

    tool = agentTools.build_agent_tool(remote_agent, user_context={"user_id": 7})

    assert isinstance(tool, agentTools.A2ATool)
    assert tool.name == "Say_Hello"
    assert tool.user_context == {"user_id": 7}


def test_a2a_tool_description_is_composed_from_all_advertised_skills():
    remote_agent = _make_agent("Remote Helper", a2a=True)
    remote_agent.a2a_config.remote_agent_metadata = {
        "skills": [
            {
                "id": "search",
                "name": "Search",
                "description": "Finds relevant information.",
                "inputModes": ["text/plain", "application/pdf"],
                "outputModes": ["text/markdown"],
                "tags": ["research", "web"],
                "examples": ["Find the latest release notes", "Summarize this attached PDF"],
            },
            {
                "id": "summarize",
                "name": "Summarize",
                "description": "Condenses long content.",
                "inputModes": ["text/plain"],
                "outputModes": ["text/plain"],
                "tags": ["summaries"],
                "examples": ["Summarize this article"],
            },
        ],
    }

    tool = agentTools.A2ATool(remote_agent)

    assert tool.description == (
        "Advertised remote skills: "
        "Search | description=Finds relevant information. | "
        "input=text/plain, application/pdf | "
        "output=text/markdown | "
        "tags=research, web | "
        "examples=Find the latest release notes; Summarize this attached PDF; "
        "Summarize | description=Condenses long content. | "
        "input=text/plain | "
        "output=text/plain | "
        "tags=summaries | "
        "examples=Summarize this article"
    )


@pytest.mark.asyncio
async def test_a2a_tool_arun_uses_executor_and_prompt_template():
    remote_agent = _make_agent("Say Hello", prompt_template="Ask this: {question}", a2a=True)
    tool = agentTools.A2ATool(remote_agent, user_context={"user_id": 5})

    with patch(
        "tools.agentTools.A2AExecutorService.execute",
        new=AsyncMock(return_value=A2AExecutionResult(text="Remote hello")),
    ) as mock_execute:
        result = await tool._arun("hello")

    assert result == "Remote hello"
    mock_execute.assert_awaited_once_with(
        remote_agent,
        "Ask this: hello",
        user_context={"user_id": 5},
    )


def test_iact_tool_wraps_nested_a2a_tools_without_local_llm_lookup():
    parent_agent = _make_agent("Coordinator")
    remote_tool_agent = _make_agent("Say Hello", a2a=True)
    parent_agent.tool_associations.append(AgentTool(tool=remote_tool_agent))

    def fake_get_llm(agent, is_vision=False):
        if agent is parent_agent:
            return object()
        raise AssertionError("Nested A2A tools should not request a local LLM")

    with (
        patch("tools.agentTools.get_llm", side_effect=fake_get_llm),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()) as mock_create_agent,
    ):
        agentTools.IACTTool(parent_agent, user_context={"user_id": 11})

    nested_tools = mock_create_agent.call_args.kwargs["tools"]
    assert any(isinstance(tool, agentTools.A2ATool) for tool in nested_tools)


def test_agent_backed_tools_expose_gemini_compatible_schema():
    remote_tool = agentTools.A2ATool(_make_agent("Remote Tool", a2a=True))

    with (
        patch("tools.agentTools.get_llm", return_value=object()),
        patch("tools.agentTools.create_langchain_agent", return_value=MagicMock()),
    ):
        local_tool = agentTools.IACTTool(_make_agent("Local Tool"))

    for tool in (remote_tool, local_tool):
        schema = tool.tool_call_schema.model_json_schema()
        assert schema["properties"] == {
            "query": {
                "description": "The request to send to the agent tool.",
                "title": "Query",
                "type": "string",
            }
        }
        assert schema["required"] == ["query"]
