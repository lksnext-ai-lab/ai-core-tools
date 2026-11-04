"""Integration tests: DB Middleware rows -> real create_agent() -> real LangGraph agent.

Only the LLM is faked. Covers that attached middlewares are applied at execution time,
that stored configs are re-validated (a bad row is skipped instead of breaking the chat)
and that a repeated type cannot crash LangChain's unique-middleware check.
"""
import pytest
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from models.middleware import Middleware, MiddlewareType, AgentMiddleware
from tools.agentTools import create_agent
from tools.middleware.factory import build_agent_middlewares

pytestmark = pytest.mark.integration


def _attach(db, app, agent, mw_type, config, name, order=0):
    middleware = Middleware(name=name, middleware_type=mw_type, config=config, app_id=app.app_id)
    db.add(middleware)
    db.flush()
    db.add(AgentMiddleware(agent_id=agent.agent_id, middleware_id=middleware.middleware_id, order=order))
    db.flush()
    db.refresh(agent)
    return middleware


async def _run_agent(agent, message="Hi there", response_text="Hello from the test LLM"):
    fake_llm = FakeListChatModel(responses=[response_text])
    with patch("tools.agentTools.get_llm", return_value=fake_llm):
        agent_chain, _ = await create_agent(agent)
    return await agent_chain.ainvoke({"messages": [HumanMessage(content=message)]}, config={})


class TestGuardrailsEndToEnd:
    @pytest.mark.asyncio
    async def test_guardrails_does_not_touch_conversation_state(self, db, fake_app, fake_agent):
        _attach(db, fake_app, fake_agent, MiddlewareType.GUARDRAILS,
                {"input": {"block_jailbreak": True}, "custom_prompt": ""}, "Guard")

        result = await _run_agent(fake_agent)

        assert not any(isinstance(m, SystemMessage) for m in result["messages"])
        assert result["messages"][-1].content == "Hello from the test LLM"


class TestPIIEndToEnd:
    @pytest.mark.asyncio
    async def test_llm_detector_redacts_alongside_regex(self, db, fake_app, fake_agent):
        from tools.middleware.llm_pii import _PIIDetectionResult, _PIIFinding

        class _FakeStructuredDetector:
            async def ainvoke(self, prompt, config=None):
                return _PIIDetectionResult(findings=[_PIIFinding(type="person", value="John Smith")])

        class _FakeDetectorLLM:
            def with_structured_output(self, schema):
                return _FakeStructuredDetector()

        _attach(db, fake_app, fake_agent, MiddlewareType.PII, {
            "pii_types": ["email"],
            "strategy": "redact",
            "apply_to_input": True,
            "apply_to_output": False,
            "apply_to_tool_results": False,
            "llm_detector": {"enabled": True, "ai_service": "ai_service:999", "extra_entities": ["person"]},
        }, "PII")

        def _resolve(agent, ref, default):
            return _FakeDetectorLLM() if ref.startswith("ai_service:") else default

        with patch("tools.middleware.factory._resolve_llm", side_effect=_resolve):
            result = await _run_agent(fake_agent, message="I'm John Smith, email me at test@example.com")

        human = [m for m in result["messages"] if isinstance(m, HumanMessage)]
        assert len(human) == 1
        assert "[REDACTED_PERSON]" in human[0].content  # LLM detector (extra_entities)
        assert "[REDACTED_EMAIL]" in human[0].content   # regex PIIMiddleware


class TestChainRobustness:
    @pytest.mark.asyncio
    async def test_invalid_stored_config_is_skipped(self, db, fake_app, fake_agent):
        _attach(db, fake_app, fake_agent, MiddlewareType.MODEL_CALL_LIMIT, {"max_calls": "abc"}, "Broken")

        assert build_agent_middlewares(fake_agent, FakeListChatModel(responses=["x"])) == []
        result = await _run_agent(fake_agent)
        assert result["messages"][-1].content == "Hello from the test LLM"

    @pytest.mark.asyncio
    async def test_repeated_type_uses_first_only(self, db, fake_app, fake_agent):
        _attach(db, fake_app, fake_agent, MiddlewareType.MODEL_CALL_LIMIT, {"max_calls": 5}, "Limit A", order=0)
        _attach(db, fake_app, fake_agent, MiddlewareType.MODEL_CALL_LIMIT, {"max_calls": 9}, "Limit B", order=1)

        chain = build_agent_middlewares(fake_agent, FakeListChatModel(responses=["x"]))

        assert [m.run_limit for m in chain] == [5]
        result = await _run_agent(fake_agent)
        assert result["messages"][-1].content == "Hello from the test LLM"

    @pytest.mark.asyncio
    async def test_chain_follows_configured_order(self, db, fake_app, fake_agent):
        _attach(db, fake_app, fake_agent, MiddlewareType.TOOL_CALL_LIMIT, {"max_calls": 3}, "Tools", order=1)
        _attach(db, fake_app, fake_agent, MiddlewareType.GUARDRAILS, {}, "Guard", order=0)

        chain = build_agent_middlewares(fake_agent, FakeListChatModel(responses=["x"]))

        assert [type(m).__name__ for m in chain] == ["GuardrailsMiddleware", "ToolCallLimitMiddleware"]


class TestNoMiddlewareEndToEnd:
    @pytest.mark.asyncio
    async def test_agent_without_middlewares_runs_without_extra_messages(self, db, fake_app, fake_agent):
        result = await _run_agent(fake_agent)

        assert not any(isinstance(m, SystemMessage) for m in result["messages"])
