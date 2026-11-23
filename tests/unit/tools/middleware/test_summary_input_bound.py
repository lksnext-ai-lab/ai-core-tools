"""The summary call's input is bounded by the model that writes the summary (Change 2).

``trim_tokens_to_summarize=None`` sent the whole older history in ONE call, which overflows the summary model after a
conversation switched to a smaller-window model.
"""
import asyncio
import copy
import time
from typing import Any
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from models.middleware import MiddlewareType
from tests.integration.internal_chat._provider_sim import PROVIDERS
from tools.middleware.factory import (
    SUMMARY_PROMPT_OVERHEAD_TOKENS,
    build_agent_middlewares,
    _is_transient_error,
    _TransientOnlyRetry,
    default_trigger_tokens,
    summary_trim_limits,
)


def _llm(window=None):
    return FakeListChatModel(responses=["ok"], profile={"max_input_tokens": window} if window else None)


def _agent(summarization_config=None, ai_services=()):
    associations = []
    if summarization_config is not None:
        associations.append(SimpleNamespace(middleware=SimpleNamespace(
            middleware_id=1, middleware_type=MiddlewareType.SUMMARIZATION, config=summarization_config)))
    return SimpleNamespace(agent_id=1, has_memory=True, middleware_associations=associations,
                           app=SimpleNamespace(ai_services=list(ai_services)))


def _summarization(chain):
    return next(m for m in chain if isinstance(m, SummarizationMiddleware))


def _conversation(total_tokens, per_message=1000):
    """Alternating human/ai messages of ~``per_message`` tokens each, about ``total_tokens`` in all."""
    messages = []
    for i in range(max(total_tokens // per_message, 1)):
        cls = HumanMessage if i % 2 == 0 else AIMessage
        messages.append(cls(content=f"{i:04d} " + "x" * (per_message * 4 - 5), id=f"m{i}"))
    return messages


class _Recorder(BaseChatModel):
    prompts: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-recorder"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage("SUMMARY"))])


def _summary_message(text="EARLIER-SUMMARY-MARKER"):
    return HumanMessage(content=f"Here is a summary of the conversation to date:\n\n{text}",
                        additional_kwargs={"lc_source": "summarization"}, id="summary")


def _mw(window=None, config=None, chat_turn=False):
    llm = _Recorder(profile={"max_input_tokens": window} if window else None)
    return _summarization(build_agent_middlewares(_agent(config), llm, chat_turn=chat_turn)), llm


class TestTrimBound:
    def test_default_is_the_summary_models_window_minus_the_overhead(self):
        mw = _summarization(build_agent_middlewares(_agent(), _llm(128_000)))

        assert mw.trim_tokens_to_summarize == 128_000 - SUMMARY_PROMPT_OVERHEAD_TOKENS

    def test_long_context_models_are_not_capped_by_the_trigger_cap(self):
        mw = _summarization(build_agent_middlewares(_agent(), _llm(1_000_000)))

        assert mw.trim_tokens_to_summarize == 1_000_000 - SUMMARY_PROMPT_OVERHEAD_TOKENS

    def test_regular_agent_without_a_profile_keeps_the_old_behaviour(self):
        assert _summarization(build_agent_middlewares(_agent(), _llm())).trim_tokens_to_summarize is None

    def test_chat_turn_without_a_profile_gets_the_conservative_bound(self):
        mw = _summarization(build_agent_middlewares(_agent(), _llm(), chat_turn=True))

        assert mw.trim_tokens_to_summarize == int(32_000 / 0.85) - SUMMARY_PROMPT_OVERHEAD_TOKENS
        assert mw.trim_tokens_to_summarize > 32_000  # above the 32k trigger: same-model history is not trimmed

    def test_tiny_window_keeps_a_usable_bound(self):
        mw = _summarization(build_agent_middlewares(_agent(), _llm(1_000)))

        assert mw.trim_tokens_to_summarize == 500

    def test_explicit_trim_tokens_wins(self):
        config = {"trigger_tokens": 8000, "keep_messages": 6, "trim_tokens": 4000}

        mw = _summarization(build_agent_middlewares(_agent(config), _llm(128_000)))

        assert mw.trim_tokens_to_summarize == 4000

    def test_a_configured_trigger_below_the_window_does_not_change_the_bound(self):
        mw = _summarization(build_agent_middlewares(_agent({"trigger_tokens": 400_000}), _llm(1_000_000)))

        assert mw.trim_tokens_to_summarize == 998_000  # window based; the trigger (400k) is below it

    def test_a_configured_trigger_above_the_window_does_not_raise_the_bound_and_warns(self):
        with patch("tools.middleware.factory.logger") as log:
            small = _summarization(build_agent_middlewares(_agent({"trigger_tokens": 130_000}), _llm(128_000)))

        assert small.trim_tokens_to_summarize == 126_000  # sending 130k whole would overflow the 128k model
        (message, *numbers), = [c.args for c in log.warning.call_args_list]
        assert numbers == [130_000, 128_000]

    def test_no_warning_when_the_trigger_fits(self):
        with patch("tools.middleware.factory.logger") as log:
            build_agent_middlewares(_agent({"trigger_tokens": 100_000}), _llm(128_000))

        log.warning.assert_not_called()

    def test_bound_is_computed_on_the_model_that_writes_the_summary(self):
        """A separate summarization model: its window, not the turn model's, sets the bound."""
        service = SimpleNamespace(service_id=7)
        config = {"summarization_model": "ai_service:7", "keep_messages": 6}
        with patch("tools.aiServiceTools.create_llm_from_service", return_value=_llm(16_000)):
            mw = _summarization(build_agent_middlewares(_agent(config, [service]), _llm(1_000_000)))

        assert mw.trigger == ("tokens", 150_000)  # the turn model decides WHEN
        assert mw.trim_tokens_to_summarize == 16_000 - SUMMARY_PROMPT_OVERHEAD_TOKENS  # the writer WHAT FITS


class TestSameModelHistoryIsNeverTrimmed:
    def test_earlier_summary_survives_when_the_kept_messages_are_tiny(self):
        """Regression: gpt-4o (128k, trigger 108,800); kept 20 messages < 2000 tokens, so the older part is just
        under the trigger and ABOVE ``trigger - overhead``. A trigger-based bound dropped the earlier summary."""
        mw, recorder = _mw(128_000)
        older = [_summary_message(), *_conversation(108_300)]
        tokens = count_tokens_approximately(older)
        assert 106_800 < tokens < 108_800, tokens

        assert mw._trim_messages_for_summary(older) == older
        asyncio.run(mw._acreate_summary(older))

        assert "EARLIER-SUMMARY-MARKER" in recorder.prompts[0][0].content

    def test_trigger_above_the_trigger_cap_is_not_trimmed(self):
        mw, recorder = _mw(1_000_000, {"trigger_tokens": 400_000, "keep_messages": 6})
        older = [_summary_message(), *_conversation(390_000)]

        assert mw._trim_messages_for_summary(older) == older

    def test_chat_turn_without_profile_same_model_history_is_not_trimmed(self):
        mw, _ = _mw(None, chat_turn=True)
        older = [_summary_message(), *_conversation(32_500)]  # just above the 32k fallback trigger

        assert mw._trim_messages_for_summary(older) == older


class TestThresholdAndTarget:
    def test_limits_for_a_128k_model(self):
        mw, _ = _mw(128_000)

        assert (mw.trim_tokens_to_summarize, mw.trim_target_tokens) == (126_000, 100_400)  # 0.8 * 128k - 2000

    def test_target_never_exceeds_the_threshold(self):
        for window, trigger in [(128_000, None), (1_000_000, 400_000), (128_000, 130_000), (1_000, None), (4_000, 9_000)]:
            threshold, target = summary_trim_limits(_llm(window), trigger)

            assert 1 <= target <= threshold, (window, trigger, threshold, target)

    def test_configured_trigger_below_the_window_changes_nothing(self):
        assert summary_trim_limits(_llm(128_000), 130_000) == (126_000, 100_400)  # trigger above the window: no raise
        assert summary_trim_limits(_llm(1_000_000), 400_000) == (998_000, 798_000)

    def test_tiny_window(self):
        assert summary_trim_limits(_llm(1_000)) == (500, 300)

    def test_explicit_trim_tokens_is_threshold_and_target(self):
        mw, _ = _mw(128_000, {"trim_tokens": 5000})

        assert (mw.trim_tokens_to_summarize, mw.trim_target_tokens) == (5000, 5000)

    def test_just_under_the_threshold_is_untouched(self):
        mw, _ = _mw(128_000)
        older = [_summary_message(), *_conversation(125_900)]
        assert count_tokens_approximately(older) <= 126_000

        result = mw._trim_messages_for_summary(older)

        assert result is older

    def test_just_over_the_threshold_is_trimmed_to_the_target_keeping_the_summary(self):
        mw, recorder = _mw(128_000)
        older = [_summary_message(), *_conversation(126_500)]
        assert count_tokens_approximately(older) > 126_000

        result = mw._trim_messages_for_summary(older)

        assert result[0] is older[0] and result[-1] is older[-1]
        assert count_tokens_approximately(result) <= mw.trim_target_tokens == 100_400
        asyncio.run(mw._acreate_summary(older))
        assert "EARLIER-SUMMARY-MARKER" in recorder.prompts[0][0].content
        assert count_tokens_approximately(recorder.prompts[0]) < 0.8 * 128_000

    def test_over_the_threshold_without_an_earlier_summary_trims_to_the_target(self):
        mw, _ = _mw(32_000)
        older = _conversation(60_000)

        result = mw._trim_messages_for_summary(older)

        assert count_tokens_approximately(result) <= mw.trim_target_tokens == 23_600
        assert result[-1] is older[-1]

    def test_explicit_trim_tokens_is_the_library_behaviour(self):
        mw, _ = _mw(128_000, {"trim_tokens": 5000})
        plain = SummarizationMiddleware(model=_llm(128_000), trim_tokens_to_summarize=5000)
        older = _conversation(50_000)

        assert [m.id for m in mw._trim_messages_for_summary(older)] == [m.id for m in plain._trim_messages_for_summary(older)]

    def test_a_summary_larger_than_the_target_falls_back_to_plain_trimming_to_the_target(self):
        mw, _ = _mw(32_000)
        plain = SummarizationMiddleware(model=_llm(32_000), trim_tokens_to_summarize=mw.trim_target_tokens)
        older = [_summary_message("x" * 160_000), *_conversation(60_000)]

        assert [m.id for m in mw._trim_messages_for_summary(older)] == [m.id for m in plain._trim_messages_for_summary(older)]

    def test_a_message_larger_than_the_target_does_not_empty_the_summary_input(self):
        mw, _ = _mw(2_000)  # threshold 1000, target 600
        older = _conversation(6_800, per_message=750)  # 9 messages, the last one human

        result = mw._trim_messages_for_summary(older)

        assert result and result[-1] is older[-1]
        assert 600 < count_tokens_approximately(result) <= 1_000

    def test_a_failing_counter_falls_back_to_the_last_messages(self):
        mw, _ = _mw(32_000)
        mw.token_counter = lambda messages: (_ for _ in ()).throw(RuntimeError("boom"))

        assert mw._trim_messages_for_summary(_conversation(5_000)) == _conversation(5_000)[-15:]

    def test_node_name_stays_the_library_one(self):
        mw, _ = _mw(32_000)

        assert mw.name == "SummarizationMiddleware"


class TestSummaryRetryOnlyForTransientErrors:
    class _Boom(Exception):
        def __init__(self, status):
            super().__init__("boom")
            self.status_code = status

    class _Failing(BaseChatModel):
        status: int = 500
        attempts: list = Field(default_factory=list)

        @property
        def _llm_type(self) -> str:
            return "failing"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self.attempts.append(1)
            raise TestSummaryRetryOnlyForTransientErrors._Boom(self.status)

    def _attempts(self, status):
        model = self._Failing(status=status)
        mw = _summarization(build_agent_middlewares(_agent(), model, chat_turn=True))
        mw._summary_model.wait_exponential_jitter = False  # no real sleeping
        with pytest.raises(self._Boom):
            asyncio.run(mw._acreate_summary(_conversation(2_000)))
        return len(model.attempts)

    @pytest.mark.parametrize("status", [400, 401, 404, 413, 422])
    def test_deterministic_client_errors_are_not_retried(self, status):
        assert self._attempts(status) == 1

    @pytest.mark.parametrize("status", [408, 429, 500, 503])
    def test_transient_errors_are_retried_three_times(self, status):
        assert self._attempts(status) == 3

    def test_status_is_read_from_the_response_too(self):
        error = Exception("x")
        error.response = SimpleNamespace(status_code=400)

        assert not _is_transient_error(error) and _is_transient_error(Exception("x"))


class TestAfterSwitchToASmallerModel:
    def test_summary_input_fits_the_small_models_window(self):
        window = 32_000
        older = _conversation(100_000)  # written under a big-window model, now summarized by a 32k one
        recorder = _Recorder(profile={"max_input_tokens": window})
        small = build_agent_middlewares(_agent(), recorder)
        mw = _summarization(small)

        asyncio.run(mw._acreate_summary(older))
        sent = recorder.prompts[0]

        assert len(sent) == 1
        assert count_tokens_approximately(sent) < window
        # The newest history is what survives the bound.
        assert older[-1].content[:4] in sent[0].content

    def test_unbounded_would_have_overflowed(self):
        """The finding: with ``None`` the same call is far above the window."""
        window = 32_000
        recorder = _Recorder(profile={"max_input_tokens": window})
        mw = SummarizationMiddleware(model=recorder, trigger=("tokens", 27_200), trim_tokens_to_summarize=None)

        asyncio.run(mw._acreate_summary(_conversation(100_000)))

        assert count_tokens_approximately(recorder.prompts[0]) > window


class TestSummaryPromptNeedsNoNormalising:
    """SummarizationMiddleware sends ONE prompt string built with ``get_buffer_string``: foreign blocks never reach
    the summary model's converter, so the history normaliser does not have to wrap that call."""

    @pytest.mark.parametrize("source", ["OpenAI", "Anthropic", "Google"])
    @pytest.mark.parametrize("target", PROVIDERS)
    def test_summary_prompt_is_accepted_by_every_converter(self, source, target):
        from tests.integration.internal_chat._provider_sim import reply, validate_for

        ai = reply(source, "", ("search", {"q": "x"}), reasoning=True)
        older = [HumanMessage("q", id="h1"), ai,
                 AIMessage(content=ai.content, id="a2", tool_calls=[], response_metadata=ai.response_metadata)]
        recorder = _Recorder()
        mw = SummarizationMiddleware(model=recorder, trigger=("tokens", 1000), trim_tokens_to_summarize=None)

        asyncio.run(mw._acreate_summary(copy.deepcopy(older)))
        sent = recorder.prompts[0]

        assert len(sent) == 1 and isinstance(sent[0].content, str)
        validate_for(target, sent)


class TestRetryNeverSwallowsCancellation:
    """tenacity hands EVERY BaseException of an attempt to the retry predicate: CancelledError, KeyboardInterrupt and
    SystemExit must never be retried, or timeouts, client disconnects and shutdown are defeated."""

    class _Slow(BaseChatModel):
        seconds: float = 1.0
        attempts: list = Field(default_factory=list)

        @property
        def _llm_type(self) -> str:
            return "slow"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self.attempts.append(1)
            import time
            time.sleep(self.seconds)
            return ChatResult(generations=[ChatGeneration(message=AIMessage("x"))])

        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            self.attempts.append(1)
            await asyncio.sleep(self.seconds)
            return ChatResult(generations=[ChatGeneration(message=AIMessage("x"))])

    class _Raises(BaseChatModel):
        error: Any = None
        attempts: list = Field(default_factory=list)

        @property
        def _llm_type(self) -> str:
            return "raises"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self.attempts.append(1)
            raise self.error

        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            self.attempts.append(1)
            raise self.error

    @staticmethod
    def _retry(model):
        retry = _TransientOnlyRetry(bound=model, kwargs={}, config={}, retry_exception_types=(Exception,),
                                    wait_exponential_jitter=False, max_attempt_number=3)
        return retry

    def test_a_timeout_around_the_call_raises_promptly_with_one_attempt(self):
        model = self._Slow(seconds=1.0)

        async def run():
            async with asyncio.timeout(0.2):
                await self._retry(model).ainvoke("hi")

        started = time.monotonic()
        with pytest.raises(TimeoutError):
            asyncio.run(run())

        assert time.monotonic() - started < 0.8 and len(model.attempts) == 1

    def test_task_cancel_propagates_with_one_attempt(self):
        model = self._Slow(seconds=1.0)

        async def run():
            task = asyncio.ensure_future(self._retry(model).ainvoke("hi"))
            await asyncio.sleep(0.2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(run())

        assert len(model.attempts) == 1

    @pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(1)])
    def test_interrupts_are_not_retried(self, error):
        for call in ("sync", "async"):
            model = self._Raises(error=error)
            with pytest.raises(type(error)):
                if call == "sync":
                    self._retry(model).invoke("hi")
                else:
                    asyncio.run(self._retry(model).ainvoke("hi"))
            assert len(model.attempts) == 1, call

    @pytest.mark.parametrize("error,attempts", [("400", 1), ("429", 3), ("500", 3), ("plain", 3)])
    def test_existing_behaviour_is_unchanged(self, error, attempts):
        exc = (RuntimeError("x") if error == "plain"
               else TestSummaryRetryOnlyForTransientErrors._Boom(int(error)))
        model = self._Raises(error=exc)

        with pytest.raises(type(exc)):
            asyncio.run(self._retry(model).ainvoke("hi"))

        assert len(model.attempts) == attempts

    def test_predicate_rejects_non_exceptions(self):
        assert not _is_transient_error(KeyboardInterrupt()) and not _is_transient_error(asyncio.CancelledError())
