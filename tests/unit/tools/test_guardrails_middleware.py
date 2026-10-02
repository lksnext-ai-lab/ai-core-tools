"""GuardrailsMiddleware: policy goes into the system prompt of each model call only.

Regression for the original implementation, which wrote SystemMessages into the agent
state: they landed between an AIMessage's tool_calls and its ToolMessage (OpenAI 400),
broke Anthropic ("multiple non-consecutive system messages"), were persisted in the
checkpoint and became the "answer" of non-streaming calls.
"""
import pytest
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from schemas.middleware_schemas import GuardrailsConfig
from tools.middleware.guardrails import GuardrailsMiddleware, compose_guardrail_policy


class _ToolCallingFake(BaseChatModel):
    """First call asks for the `add` tool, second call answers. Records every request."""

    calls: list = []

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self) -> str:
        return "fake-tool-calling"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(list(messages))
        if len(self.calls) == 1:
            msg = AIMessage(content="", tool_calls=[{"name": "add", "args": {"a": 1, "b": 2}, "id": "call_1"}])
        else:
            msg = AIMessage(content="The result is 3")
        return ChatResult(generations=[ChatGeneration(message=msg)])


@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


class TestComposePolicy:
    def test_all_rules_enabled_by_default(self):
        policy = compose_guardrail_policy(GuardrailsConfig())
        assert policy.startswith("<guardrails>")
        assert "jailbreak" in policy and "personally identifiable" in policy

    def test_nothing_enabled_returns_none(self):
        cfg = GuardrailsConfig(
            input={"block_malicious_prompts": False, "block_jailbreak": False},
            output={"prevent_pii_leakage": False, "block_toxic_biased": False, "enforce_business_facts": False},
        )
        assert compose_guardrail_policy(cfg) is None

    def test_custom_prompt_included(self):
        cfg = GuardrailsConfig(custom_prompt="Only talk about invoices.")
        assert "Only talk about invoices." in compose_guardrail_policy(cfg)


class TestGuardrailsInAgent:
    @pytest.mark.asyncio
    async def test_policy_is_in_system_prompt_and_state_is_untouched(self):
        model = _ToolCallingFake()
        model.calls = []
        agent = create_agent(
            model,
            tools=[add],
            system_prompt="You are a calculator.",
            middleware=[GuardrailsMiddleware(GuardrailsConfig())],
        )

        result = await agent.ainvoke({"messages": [HumanMessage("what is 1+2?")]})

        assert len(model.calls) == 2
        for sent in model.calls:
            # Exactly one system message, first, holding agent prompt + policy.
            assert isinstance(sent[0], SystemMessage)
            assert [m for m in sent if isinstance(m, SystemMessage)] == [sent[0]]
            assert "You are a calculator." in sent[0].text
            assert "<guardrails>" in sent[0].text
        # tool_calls are followed directly by their ToolMessage.
        second = model.calls[1]
        ai_idx = next(i for i, m in enumerate(second) if isinstance(m, AIMessage))
        assert isinstance(second[ai_idx + 1], ToolMessage)
        # Nothing was written to the conversation state; the answer is the last message.
        assert not any(isinstance(m, SystemMessage) for m in result["messages"])
        assert result["messages"][-1].content == "The result is 3"

    @pytest.mark.asyncio
    async def test_works_without_agent_system_prompt(self):
        model = _ToolCallingFake()
        model.calls = []
        agent = create_agent(model, tools=[add], middleware=[GuardrailsMiddleware(GuardrailsConfig())])

        await agent.ainvoke({"messages": [HumanMessage("what is 1+2?")]})

        assert isinstance(model.calls[0][0], SystemMessage)
        assert model.calls[0][0].text.startswith("<guardrails>")
