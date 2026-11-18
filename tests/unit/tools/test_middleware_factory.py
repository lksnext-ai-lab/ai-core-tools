"""Unit tests for the agent middleware chain: summarization defaults and agents used as tools."""
from types import SimpleNamespace

from langchain.agents.middleware import HumanInTheLoopMiddleware, SummarizationMiddleware
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from models.middleware import MiddlewareType
from tools.middleware.factory import build_agent_middlewares, default_trigger_tokens, tools_needing_approval


def _llm(max_input_tokens=None):
    profile = {"max_input_tokens": max_input_tokens} if max_input_tokens else None
    return FakeListChatModel(responses=["ok"], profile=profile)


def _agent(has_memory=True, summarization_config=None, approval_config=None):
    associations = []
    if summarization_config is not None:
        middleware = SimpleNamespace(
            middleware_id=1, middleware_type=MiddlewareType.SUMMARIZATION, config=summarization_config,
        )
        associations.append(SimpleNamespace(middleware=middleware))
    if approval_config is not None:
        middleware = SimpleNamespace(
            middleware_id=2, middleware_type=MiddlewareType.HUMAN_IN_THE_LOOP, config=approval_config,
        )
        associations.append(SimpleNamespace(middleware=middleware))
    return SimpleNamespace(agent_id=1, has_memory=has_memory, middleware_associations=associations, app=None)


def _summarization(chain):
    return next((m for m in chain if isinstance(m, SummarizationMiddleware)), None)


class TestDefaultTriggerTokens:
    def test_uses_85_percent_of_the_model_window(self):
        assert default_trigger_tokens(_llm(128_000)) == 108_800

    def test_caps_long_context_models(self):
        assert default_trigger_tokens(_llm(1_047_576)) == 150_000

    def test_falls_back_without_a_model_profile(self):
        assert default_trigger_tokens(_llm()) == 32_000


class TestDefaultSummarization:
    def test_agent_with_memory_gets_the_defaults(self):
        middleware = _summarization(build_agent_middlewares(_agent(), _llm(128_000)))

        assert middleware.trigger == ("tokens", 108_800)
        assert middleware.keep == ("messages", 20)
        assert middleware.trim_tokens_to_summarize is None

    def test_agent_without_memory_gets_none(self):
        assert build_agent_middlewares(_agent(has_memory=False), _llm(128_000)) == []


class TestAttachedSummarization:
    def test_explicit_values_are_used(self):
        config = {"trigger_tokens": 8000, "keep_messages": 6, "trim_tokens": 4000}
        middleware = _summarization(build_agent_middlewares(_agent(summarization_config=config), _llm(128_000)))

        assert middleware.trigger == ("tokens", 8000)
        assert middleware.keep == ("messages", 6)
        assert middleware.trim_tokens_to_summarize == 4000

    def test_empty_trigger_and_trim_use_the_defaults(self):
        config = {"trigger_tokens": None, "keep_messages": 10, "trim_tokens": None}
        middleware = _summarization(build_agent_middlewares(_agent(summarization_config=config), _llm(200_000)))

        assert middleware.trigger == ("tokens", 150_000)
        assert middleware.trim_tokens_to_summarize is None


class TestAgentUsedAsTool:
    APPROVAL = {"interrupt_on": {"delete_file": {"allowed_decisions": ["approve", "reject"]}}}

    def test_human_approval_is_left_out_when_the_run_cannot_pause(self):
        agent = _agent(approval_config=self.APPROVAL)

        with_approval = build_agent_middlewares(agent, _llm(128_000))
        without_approval = build_agent_middlewares(agent, _llm(128_000), include_human_approval=False)

        assert any(isinstance(m, HumanInTheLoopMiddleware) for m in with_approval)
        assert not any(isinstance(m, HumanInTheLoopMiddleware) for m in without_approval)

    def test_tools_needing_approval(self):
        assert tools_needing_approval(_agent(approval_config=self.APPROVAL)) == {"delete_file"}
        assert tools_needing_approval(_agent()) == set()
