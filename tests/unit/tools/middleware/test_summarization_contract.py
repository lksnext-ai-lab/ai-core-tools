"""The bounded-summary subclass reads PRIVATE names of langchain: pin them, and prove the fallback.

Re-check this file on EVERY langchain / langchain-core bump: if a contract test fails, the subclass would silently
stop bounding the summary input (production falls back to the plain library middleware with one WARNING).
"""
from types import SimpleNamespace
from unittest.mock import patch

from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables.retry import RunnableRetry

import tools.middleware.factory as factory
from models.middleware import MiddlewareType


def _library_instance():
    return SummarizationMiddleware(
        model=FakeListChatModel(responses=["ok"]), trigger=("tokens", 1000), keep=("messages", 5),
        trim_tokens_to_summarize=500,
    )


def test_the_private_names_the_subclass_reads_exist_in_the_installed_langchain():
    mw = _library_instance()
    retry = mw._summary_model
    assert isinstance(retry, RunnableRetry)
    for attr in ("wait_exponential_jitter", "max_attempt_number"):
        assert hasattr(retry, attr), attr
    for attr in ("model", "trim_tokens_to_summarize", "token_counter"):
        assert hasattr(mw, attr), attr
    assert callable(getattr(mw, "_trim_messages_for_summary", None))
    assert isinstance(getattr(RunnableRetry, "_kwargs_retrying", None), property)  # the tenacity hook we override


def test_the_real_subclass_builds_with_the_installed_classes():
    mw = factory._SummarizationKeepingEarlierSummary(
        model=FakeListChatModel(responses=["ok"]), trigger=("tokens", 1000), keep=("messages", 5),
        trim_tokens_to_summarize=500, trim_target_tokens=300,
    )
    assert isinstance(mw._summary_model, factory._TransientOnlyRetry) and mw.trim_target_tokens == 300


def _agent():
    return SimpleNamespace(agent_id=1, has_memory=True, middleware_associations=[],
                           app=SimpleNamespace(ai_services=[]))


def test_a_missing_private_name_falls_back_to_the_plain_middleware_with_one_warning(monkeypatch):
    monkeypatch.setattr(factory, "_fallback_warned", False)
    llm = FakeListChatModel(responses=["ok"], profile={"max_input_tokens": 100_000})
    warnings = []
    with patch.object(factory._SummarizationKeepingEarlierSummary, "__init__",
                      side_effect=AttributeError("no _summary_model")), \
         patch.object(factory.logger, "warning", side_effect=lambda m, *a: warnings.append(m % a)):
        first = factory._summarization(_agent(), llm, None)
        second = factory._summarization(_agent(), llm, None)
    assert type(first) is SummarizationMiddleware and type(second) is SummarizationMiddleware
    assert len(warnings) == 1 and "AttributeError" in warnings[0] and "no _summary_model" not in warnings[0]
