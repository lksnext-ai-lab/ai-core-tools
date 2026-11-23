"""HistoryNormalizerMiddleware: a chat thread that switches provider keeps working.

Offline, with the REAL converters of every provider (``_provider_sim.validate_for``) and the message shapes the REAL
adapters produce (``_provider_sim.reply``). No provider is called.
"""
import asyncio
import copy
import logging
import itertools

import pytest
from unittest.mock import patch
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import Field

from tests.integration.internal_chat._provider_sim import (
    PROVIDERS,
    ProviderRejected,
    check_tool_pairing,
    real_model,
    reply,
    validate_for,
)
from tools.middleware import history_normalizer as hn
from tools.middleware.history_normalizer import (
    INTERRUPTED_TOOL_TEXT,
    PLACEHOLDER_TEXT,
    HistoryNormalizerMiddleware,
    model_family,
    normalize_history,
)

FAMILY = {
    "OpenAI": hn.OPENAI_RESPONSES, "Anthropic": hn.ANTHROPIC, "MistralAI": hn.MISTRALAI, "Azure": hn.AZURE_AI,
    "Google": hn.GOOGLE_GENAI, "Custom": hn.OLLAMA,
}
VARIANTS = ["plain", "tool", "tool_with_text", "reasoning_only"]
PAIRS = [(a, b) for a in PROVIDERS for b in PROVIDERS]


def history(provider: str, variant: str, reasoning: bool) -> list:
    """Human, provider's answer(s), Human: a complete earlier turn followed by the new question."""
    if variant in ("tool", "tool_with_text"):
        text = "let me search" if variant == "tool_with_text" else ""
        ai = reply(provider, text, ("search", {"q": "x"}), reasoning=reasoning)
        call = ai.tool_calls[0]
        return [
            HumanMessage("q"), ai, ToolMessage("result", tool_call_id=call["id"], name="search"),
            reply(provider, "the answer", reasoning=reasoning), HumanMessage("q2"),
        ]
    if variant == "reasoning_only":
        return [HumanMessage("q"), reply(provider, "", reasoning=reasoning), HumanMessage("q2")]
    return [HumanMessage("q"), reply(provider, "the answer", reasoning=reasoning), HumanMessage("q2")]


def view(provider_b: str, messages: list, **kwargs) -> list:
    return normalize_history(messages, model_family(real_model(provider_b)), **kwargs)


# ------------------------------------------------------------------ family detection


class TestFamilyDetection:
    @pytest.mark.parametrize("provider", PROVIDERS)
    def test_model_family_of_the_real_classes(self, provider):
        assert model_family(real_model(provider)) == FAMILY[provider]

    def test_openai_without_responses_api_is_chat_completions(self):
        from langchain_openai import ChatOpenAI

        custom = ChatOpenAI(model="x", api_key="x", base_url="http://gw.invalid/v1", use_responses_api=False)
        assert model_family(custom) == hn.OPENAI_CHAT
        assert model_family(ChatOpenAI(model="gpt-4o", api_key="x", use_responses_api=True)) == hn.OPENAI_RESPONSES

    def test_openai_auto_switches_to_responses_with_a_builtin_tool(self):
        from langchain_openai import ChatOpenAI

        auto = ChatOpenAI(model="gpt-4o", api_key="x")
        assert model_family(auto, [{"type": "function", "function": {}}]) == hn.OPENAI_CHAT
        assert model_family(auto, [{"type": "web_search"}]) == hn.OPENAI_RESPONSES

    def test_unknown_model_is_not_a_family(self):
        assert model_family(object()) is None

    @pytest.mark.parametrize("provider", PROVIDERS)
    def test_message_family_from_response_metadata(self, provider):
        message = reply(provider, "hi", reasoning=False)
        expected = {"Azure": None}.get(provider, FAMILY[provider])
        assert hn._message_family(message) == expected

    def test_openai_chat_completions_message_is_not_responses(self):
        chat = AIMessage("hi", response_metadata={"model_provider": "openai", "finish_reason": "stop"})
        assert hn._message_family(chat) == hn.OPENAI_CHAT


# ------------------------------------------------------------------ the provider matrix


class TestEveryOrderedProviderPair:
    @pytest.mark.parametrize("reasoning", [True, False])
    @pytest.mark.parametrize("variant", VARIANTS)
    @pytest.mark.parametrize("a,b", PAIRS)
    def test_history_written_by_a_is_accepted_by_b(self, a, b, variant, reasoning):
        messages = history(a, variant, reasoning)

        validate_for(b, view(b, messages))

    @pytest.mark.parametrize("a,b", [("OpenAI", "Custom"), ("OpenAI", "Google"), ("Anthropic", "Custom"),
                                     ("Google", "Custom"), ("OpenAI", "Azure"), ("Anthropic", "Azure")])
    def test_the_raw_history_does_fail_there(self, a, b):
        """Guards the matrix against being vacuous: without the normaliser these pairs break."""
        failures = []
        for variant, reasoning in itertools.product(VARIANTS, [True, False]):
            try:
                validate_for(b, history(a, variant, reasoning))
            except Exception as exc:  # noqa: BLE001 - the converter's own exception
                failures.append(exc)
        assert failures, f"{a} -> {b}: the raw history is accepted, the matrix proves nothing"

    @pytest.mark.parametrize("b", ["MistralAI", "Azure"])
    @pytest.mark.parametrize("a", PROVIDERS)
    def test_pass_through_providers_only_get_string_content(self, a, b):
        """Mistral and Azure forward list content to the wire: after the view, no AIMessage has any."""
        for variant in VARIANTS:
            for message in view(b, history(a, variant, True)):
                if isinstance(message, AIMessage):
                    assert isinstance(message.content, str), (a, b, variant, message.content)
                    assert not (message.additional_kwargs.keys() - {"tool_calls"})


# ------------------------------------------------------------------ the rules


class TestRules:
    @pytest.mark.parametrize("variant", VARIANTS)
    @pytest.mark.parametrize("provider", PROVIDERS)
    def test_same_family_messages_are_the_same_objects(self, provider, variant):
        messages = history(provider, variant, True)

        result = view(provider, messages)

        assert len(result) == len(messages)
        assert all(a is b for a, b in zip(result, messages))

    def test_only_foreign_messages_are_replaced(self):
        mine = reply("Anthropic", "mine", reasoning=True)
        theirs = reply("OpenAI", "theirs", ("search", {"q": "x"}))
        tool = ToolMessage("r", tool_call_id=theirs.tool_calls[0]["id"], name="search")
        messages = [HumanMessage("q"), theirs, tool, mine, HumanMessage("q2")]

        result = view("Anthropic", messages)

        assert result[3] is mine and result[2] is tool and result[0] is messages[0]
        assert result[1] is not theirs

    @pytest.mark.parametrize("a", ["OpenAI", "Anthropic", "Google", "MistralAI", "Custom", "Azure"])
    def test_tool_call_pairing_and_ids_are_preserved(self, a):
        messages = history(a, "tool_with_text", True)
        ids = [tc["id"] for m in messages if isinstance(m, AIMessage) for tc in m.tool_calls]

        for b in PROVIDERS:
            result = view(b, messages)

            check_tool_pairing(result)
            assert [tc["id"] for m in result if isinstance(m, AIMessage) for tc in m.tool_calls] == ids
            call = next(m for m in result if isinstance(m, AIMessage) and m.tool_calls)
            assert call.tool_calls == next(m for m in messages if isinstance(m, AIMessage) and m.tool_calls).tool_calls
            assert [m.tool_call_id for m in result if isinstance(m, ToolMessage)] == ids

    def test_text_message_id_name_and_usage_are_kept(self):
        original = reply("OpenAI", "the answer", reasoning=True)
        original.name = "bot"

        converted = view("Custom", [HumanMessage("q"), original, HumanMessage("q2")])[1]

        assert converted.content == "the answer"
        assert converted.id == original.id and converted.name == "bot"
        assert converted.usage_metadata == original.usage_metadata
        assert converted.additional_kwargs == {}

    def test_gemini_thought_signatures_and_reasoning_kwargs_are_dropped(self):
        message = reply("Google", "answer", ("search", {"q": "x"}))
        message.additional_kwargs["__gemini_function_call_thought_signatures__"] = {"call": "c2ln"}
        messages = [HumanMessage("q"), message, ToolMessage("r", tool_call_id=message.tool_calls[0]["id"]),
                    HumanMessage("q2")]

        converted = view("OpenAI", messages)[1]

        assert converted.additional_kwargs == {} and converted.content == "answer"
        validate_for("OpenAI", view("OpenAI", messages))

    @pytest.mark.parametrize("a", ["OpenAI", "Anthropic", "Google"])
    @pytest.mark.parametrize("b", PROVIDERS)
    def test_reasoning_only_message_gets_a_placeholder(self, a, b):
        messages = history(a, "reasoning_only", True)
        if FAMILY[a] == FAMILY[b]:
            pytest.skip("own family: untouched")

        converted = view(b, messages)[1]

        assert converted.content == PLACEHOLDER_TEXT and not converted.tool_calls
        assert [m.type for m in view(b, messages)] == ["human", "ai", "human"]
        validate_for(b, view(b, messages))

    def test_tool_call_without_text_keeps_empty_content(self):
        messages = history("OpenAI", "tool", True)

        assert view("Anthropic", messages)[1].content == ""
        validate_for("Anthropic", view("Anthropic", messages))

    def test_string_message_with_no_provider_data_is_left_alone(self):
        plain = reply("Anthropic", "hello", reasoning=False)

        assert view("Custom", [plain])[0] is plain

    def test_unknown_tag_with_list_content_is_foreign(self):
        legacy = AIMessage(content=[{"type": "reasoning", "id": "rs_1", "summary": []},
                                    {"type": "text", "text": "hi"}])

        result = view("Custom", [HumanMessage("q"), legacy, HumanMessage("q2")])

        assert result[1].content == "hi"
        validate_for("Custom", result)

    def test_unknown_model_leaves_history_alone(self):
        messages = history("OpenAI", "plain", True)

        result = normalize_history(messages, None)

        assert all(a is b for a, b in zip(result, messages))

    @pytest.mark.parametrize("b", PROVIDERS)
    def test_tool_message_content_lists_are_accepted_everywhere(self, b):
        """Rule 6: looked for a ToolMessage shape a converter rejects; none (our tools, not the adapters, write them)."""
        ai = AIMessage("", tool_calls=[{"name": "s", "args": {}, "id": "call_1"}])
        content = [{"type": "text", "text": "res", "id": "lc_1"}]
        validate_for(b, [HumanMessage("q"), ai, ToolMessage(content, tool_call_id="call_1", name="s"), HumanMessage("q2")])


class TestInterruptedToolCalls:
    ORPHAN = [HumanMessage("q"), AIMessage("", tool_calls=[{"name": "s", "args": {}, "id": "call_1"}]),
              HumanMessage("q2")]

    @pytest.mark.parametrize("b", PROVIDERS)
    def test_orphan_call_gets_a_synthetic_error_result_right_after_it(self, b):
        with pytest.raises(ProviderRejected):
            validate_for(b, self.ORPHAN)

        result = view(b, self.ORPHAN, patch_interrupted_tool_calls=True)

        assert [m.type for m in result] == ["human", "ai", "tool", "human"]
        assert result[2].tool_call_id == "call_1" and result[2].status == "error"
        assert result[2].content == INTERRUPTED_TOOL_TEXT
        validate_for(b, result)

    def test_only_the_missing_results_of_a_parallel_call_are_added(self):
        ai = AIMessage("", tool_calls=[{"name": "s", "args": {}, "id": "c1"}, {"name": "s", "args": {}, "id": "c2"}])
        answered = ToolMessage("r1", tool_call_id="c1", name="s")

        result = normalize_history([HumanMessage("q"), ai, answered, HumanMessage("q2")], None,
                                   patch_interrupted_tool_calls=True)

        assert [m.type for m in result] == ["human", "ai", "tool", "tool", "human"]
        assert result[2] is answered and result[3].tool_call_id == "c2"

    def test_complete_history_is_untouched(self):
        messages = history("OpenAI", "tool", True)

        result = view("OpenAI", messages, patch_interrupted_tool_calls=True)

        assert all(a is b for a, b in zip(result, messages)) and len(result) == len(messages)

    def test_patching_is_off_by_default(self):
        """Regular agents: a pending tool call (HITL pause, stale checkpoint) is left to the existing recovery."""
        assert HistoryNormalizerMiddleware().patch_interrupted_tool_calls is False
        assert view("Anthropic", self.ORPHAN)[1] is self.ORPHAN[1]
        assert len(view("Anthropic", self.ORPHAN)) == 3


class TestNothingIsMutated:
    @pytest.mark.parametrize("a,b", [("OpenAI", "Custom"), ("Google", "Anthropic"), ("Anthropic", "OpenAI")])
    def test_input_list_and_messages_are_unchanged(self, a, b):
        messages = history(a, "tool_with_text", True) + [AIMessage("", tool_calls=[
            {"name": "s", "args": {}, "id": "orphan"}]), HumanMessage("q3")]
        snapshot = copy.deepcopy(messages)
        original_list = list(messages)

        result = view(b, messages, patch_interrupted_tool_calls=True)

        assert result is not messages and messages == original_list
        assert all(x is y for x, y in zip(messages, original_list))
        assert messages == snapshot
        assert [m.model_dump() for m in messages] == [m.model_dump() for m in snapshot]


# ------------------------------------------------------------------ the middleware inside a real agent graph


class _Recorder(BaseChatModel):
    """Answers scripted AIMessages; records what reached it. ``_llm_type`` is Ollama's, so the family is Ollama."""

    script: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self) -> str:
        return "ollama-chat"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(copy.deepcopy(list(messages)))
        return ChatResult(generations=[ChatGeneration(message=self.script.pop(0))])


@tool
def search(q: str) -> str:
    """Search."""
    return f"found {q}"


class TestInsideAgentGraph:
    def _run(self, model, past, **mw_kwargs):
        agent = create_agent(
            model=model, tools=[search], checkpointer=InMemorySaver(),
            middleware=[HistoryNormalizerMiddleware(**mw_kwargs)],
        )
        config = {"configurable": {"thread_id": "t"}}
        agent.invoke({"messages": past}, config)
        return agent, config

    def test_model_gets_plain_history_and_the_checkpoint_keeps_the_original_blocks(self):
        past = history("OpenAI", "tool_with_text", True)[:-1]
        originals = copy.deepcopy(past)
        model = _Recorder(script=[AIMessage("fine")])

        agent, config = self._run(model, past + [HumanMessage("next")])

        for message in model.calls[0]:
            assert not isinstance(message.content, list)
        validate_for("Custom", model.calls[0])
        stored = agent.get_state(config).values["messages"]
        for kept, original in zip(stored, originals):  # reasoning / msg_ / function_call blocks intact
            assert kept.content == original.content
            assert kept.response_metadata == original.response_metadata
            assert getattr(kept, "tool_calls", None) == getattr(original, "tool_calls", None)
        assert isinstance(stored[1].content, list)

    def test_async_path_is_the_same(self):
        past = history("Google", "plain", True)[:-1]
        model = _Recorder(script=[AIMessage("fine")])
        agent = create_agent(model=model, tools=[search], middleware=[HistoryNormalizerMiddleware()])

        asyncio.run(agent.ainvoke({"messages": past + [HumanMessage("next")]}))

        assert all(not isinstance(m.content, list) for m in model.calls[0])
        validate_for("Custom", model.calls[0])

    def test_interrupted_turn_is_patched_in_the_view_only(self):
        past = [HumanMessage("q"), AIMessage("", tool_calls=[{"name": "search", "args": {"q": "x"}, "id": "call_1"}])]
        model = _Recorder(script=[AIMessage("fine")])

        agent, config = self._run(model, past + [HumanMessage("next")], patch_interrupted_tool_calls=True)

        assert [m.type for m in model.calls[0]] == ["human", "ai", "tool", "human"]
        validate_for("Custom", model.calls[0])
        assert [m.type for m in agent.get_state(config).values["messages"]] == ["human", "ai", "human", "ai"]

    def test_human_approval_pause_and_resume_are_not_disturbed(self):
        """The model is not called while an approval is pending, and on resume the call is answered: nothing to patch."""
        call = AIMessage("", tool_calls=[{"name": "search", "args": {"q": "x"}, "id": "call_1"}])
        model = _Recorder(script=[call, AIMessage("done")])
        agent = create_agent(
            model=model, tools=[search], checkpointer=InMemorySaver(),
            middleware=[HumanInTheLoopMiddleware(interrupt_on={"search": True}),
                        HistoryNormalizerMiddleware(patch_interrupted_tool_calls=True)],
        )
        config = {"configurable": {"thread_id": "t"}}

        paused = agent.invoke({"messages": [HumanMessage("go")]}, config)

        assert "__interrupt__" in paused and len(model.calls) == 1
        agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config)
        assert len(model.calls) == 2
        assert [m.type for m in model.calls[1]] == ["human", "ai", "tool"]
        assert model.calls[1][2].status != "error" and "found x" in model.calls[1][2].content


class TestMiddlewareOrder:
    def test_chat_chain_ends_with_the_normaliser_and_regular_chain_has_none(self):
        from types import SimpleNamespace
        from langchain_core.language_models.fake_chat_models import FakeListChatModel
        from tools.middleware.factory import build_agent_middlewares

        agent = SimpleNamespace(agent_id=1, has_memory=True, middleware_associations=[], app=None)
        llm = FakeListChatModel(responses=["x"], profile={"max_input_tokens": 128_000})

        chat = build_agent_middlewares(agent, llm, ignore_agent_middlewares=True, chat_turn=True,
                                       service_id=5, model_name="gpt-4o")
        regular = build_agent_middlewares(agent, llm)

        assert isinstance(chat[-1], HistoryNormalizerMiddleware) and chat[-1].patch_interrupted_tool_calls
        assert len(chat) == 2
        assert (chat[-1].service_id, chat[-1].model_name) == (5, "gpt-4o")
        assert not any(isinstance(m, HistoryNormalizerMiddleware) for m in regular)


# ------------------------------------------------------------------ round 2: stamp, robustness, details

from langchain.agents.middleware import ModelRequest, ModelResponse  # noqa: E402
from langchain.agents.middleware.types import ExtendedModelResponse  # noqa: E402
from langchain_core.messages import AIMessageChunk  # noqa: E402

STAMP_A = (1, "gpt-5")
STAMP_B = (2, "gpt-4.1")


def stamped(message, stamp):
    message.response_metadata = {**message.response_metadata, hn.STAMP_SERVICE_KEY: stamp[0],
                                 hn.STAMP_MODEL_KEY: stamp[1]}
    return message


class TestStampRule:
    def _openai_history(self, stamp):
        ai = stamped(reply("OpenAI", "", ("search", {"q": "x"}), reasoning=True), stamp)
        return [HumanMessage("q"), ai, ToolMessage("r", tool_call_id=ai.tool_calls[0]["id"], name="search"),
                stamped(reply("OpenAI", "answer", reasoning=True), stamp), HumanMessage("q2")]

    def _view(self, messages, turn_stamp):
        return normalize_history(messages, hn.OPENAI_RESPONSES, turn_stamp=turn_stamp)

    def test_same_family_and_same_stamp_is_identity(self):
        messages = self._openai_history(STAMP_A)

        result = self._view(messages, STAMP_A)

        assert all(a is b for a, b in zip(result, messages)) and len(result) == len(messages)
        validate_for("OpenAI", result)  # the extra response_metadata keys do not bother the converter

    def test_same_family_other_service_is_rewritten_and_accepted(self):
        messages = self._openai_history(STAMP_A)

        for turn in ((2, "gpt-5"), (1, "gpt-4.1")):  # other service / other model of the same provider
            result = self._view(messages, turn)

            assert result[1] is not messages[1] and result[3] is not messages[3]
            assert all(isinstance(m.content, str) for m in result if isinstance(m, AIMessage))
            assert [tc["id"] for tc in result[1].tool_calls] == [tc["id"] for tc in messages[1].tool_calls]
            validate_for("OpenAI", result)

    def test_unstamped_list_content_is_foreign_when_the_turn_has_a_stamp(self):
        messages = history("OpenAI", "tool_with_text", True)  # written before the stamp existed

        result = self._view(messages, STAMP_A)

        assert all(isinstance(m.content, str) for m in result if isinstance(m, AIMessage))

    def test_unstamped_plain_string_is_kept(self):
        plain = reply("Anthropic", "hello", reasoning=False)

        assert normalize_history([plain], hn.ANTHROPIC, turn_stamp=STAMP_A)[0] is plain

    def test_without_a_turn_stamp_same_family_is_own(self):
        messages = history("OpenAI", "tool", True)

        assert all(a is b for a, b in zip(self._view(messages, None), messages))

    def _request(self, model, messages):
        return ModelRequest(model=model, messages=messages, tools=[], state={"messages": messages})

    def test_answer_is_stamped_on_a_copy_for_every_handler_result_shape(self):
        mw = HistoryNormalizerMiddleware(service_id=7, model_name="m")
        raw = AIMessage("hi", response_metadata={"model_provider": "ollama"})
        request = self._request(real_model("Custom"), [HumanMessage("q")])
        expected = {hn.STAMP_SERVICE_KEY: 7, hn.STAMP_MODEL_KEY: "m", "model_provider": "ollama"}

        as_message = mw.wrap_model_call(request, lambda r: raw)
        as_response = mw.wrap_model_call(request, lambda r: ModelResponse(result=[raw], structured_response={"a": 1}))
        as_extended = mw.wrap_model_call(request, lambda r: ExtendedModelResponse(
            model_response=ModelResponse(result=[raw, ToolMessage("t", tool_call_id="x")])))

        assert as_message.response_metadata == expected
        assert as_response.result[0].response_metadata == expected and as_response.structured_response == {"a": 1}
        assert as_extended.model_response.result[0].response_metadata == expected
        assert isinstance(as_extended.model_response.result[1], ToolMessage)
        assert raw.response_metadata == {"model_provider": "ollama"}  # the model's object is untouched
        assert as_message.id == raw.id

    def test_no_stamp_without_a_service(self):
        raw = AIMessage("hi")

        assert HistoryNormalizerMiddleware().wrap_model_call(
            self._request(real_model("Custom"), [HumanMessage("q")]), lambda r: raw) is raw

    def test_stamp_survives_streaming_aggregation_and_the_checkpoint_round_trip(self):
        class Streamer(_Recorder):
            def _stream(self, messages, stop=None, run_manager=None, **kwargs):
                from langchain_core.outputs import ChatGenerationChunk

                for word in ("hel", "lo"):
                    yield ChatGenerationChunk(message=AIMessageChunk(
                        content=word, response_metadata={"model_provider": "ollama"}))

        model = Streamer()
        saver = InMemorySaver()
        agent = create_agent(model=model, tools=[search], checkpointer=saver,
                             middleware=[HistoryNormalizerMiddleware(service_id=3, model_name="llama")])
        config = {"configurable": {"thread_id": "s"}}

        async def run():
            async for _ in agent.astream({"messages": [HumanMessage("q")]}, config, stream_mode="messages"):
                pass

        asyncio.run(run())
        # A fresh graph over the same checkpointer: what a later turn reads back.
        fresh = create_agent(model=_Recorder(), tools=[search], checkpointer=saver)
        stored = fresh.get_state(config).values["messages"][-1]

        assert stored.content == "hello"
        assert stored.response_metadata[hn.STAMP_SERVICE_KEY] == 3 and stored.response_metadata[hn.STAMP_MODEL_KEY] == "llama"

    @pytest.mark.parametrize("provider", PROVIDERS)
    def test_stamped_messages_pass_every_converter(self, provider):
        messages = [HumanMessage("q"), stamped(reply(provider, "answer", reasoning=True), STAMP_A), HumanMessage("q2")]

        validate_for(provider, normalize_history(messages, model_family(real_model(provider)), turn_stamp=STAMP_A))


class TestRobustness:
    def test_a_failing_view_passes_the_request_through_and_logs_only_the_class(self):
        mw = HistoryNormalizerMiddleware()
        request = ModelRequest(model=real_model("Custom"), messages=[HumanMessage("secret text")], tools=[],
                               state={"messages": []})
        seen = []

        with patch.object(hn, "normalize_history", side_effect=RuntimeError("secret text")), \
                patch.object(hn, "logger") as log:
            mw.wrap_model_call(request, lambda r: seen.append(r) or AIMessage("x"))

        assert seen == [request]
        logged = [str(c) for c in log.warning.call_args_list]
        assert logged and "RuntimeError" in logged[0] and "secret text" not in logged[0]

    def test_debug_log_has_numbers_only(self):
        messages = history("OpenAI", "tool", True)[:-1]
        with patch.object(hn, "logger") as log:
            view("Custom", messages, patch_interrupted_tool_calls=True)

        level, _message, rewritten, patched = log.log.call_args.args
        assert (rewritten, patched) == (2, 0) and level == logging.INFO  # non-zero: INFO

    def test_zero_counts_are_logged_at_debug(self):
        with patch.object(hn, "logger") as log:
            view("OpenAI", history("OpenAI", "plain", True))

        assert log.log.call_args.args[0] == logging.DEBUG

    def test_multiple_text_blocks_are_joined_with_newlines(self):
        message = AIMessage(content=[{"type": "reasoning", "summary": []}, {"type": "text", "text": "a"},
                                     {"type": "text", "text": "b"}], response_metadata={"model_provider": "openai"})

        assert normalize_history([message], hn.OLLAMA)[0].content == "a\nb"

    def test_refusal_only_turn_keeps_its_text(self):
        message = AIMessage(content=[{"type": "refusal", "refusal": "I cannot help with that"}],
                            response_metadata={"model_provider": "openai"})

        assert normalize_history([message], hn.OLLAMA)[0].content == "I cannot help with that"

    def test_tool_calls_are_copied(self):
        original = reply("OpenAI", "", ("search", {"q": "x"}))

        converted = normalize_history([original], hn.OLLAMA)[0]

        assert converted.tool_calls == original.tool_calls
        assert converted.tool_calls[0] is not original.tool_calls[0]

    def test_reused_tool_call_id_is_patched_per_message(self):
        first = AIMessage("", tool_calls=[{"name": "s", "args": {}, "id": "call_1"}])
        second = AIMessage("", tool_calls=[{"name": "s", "args": {}, "id": "call_1"}])
        answered = ToolMessage("r", tool_call_id="call_1", name="s")

        result = normalize_history([HumanMessage("q"), first, answered, HumanMessage("q2"), second, HumanMessage("q3")],
                                   None, patch_interrupted_tool_calls=True)

        assert [m.type for m in result] == ["human", "ai", "tool", "human", "ai", "tool", "human"]
        assert result[2] is answered and result[5].status == "error"

    def test_unwrap_goes_through_a_real_runnable_binding(self):
        base = real_model("Custom")
        bound = base.bind(stop=["x"])

        from langchain_core.runnables import RunnableBinding

        assert isinstance(bound, RunnableBinding)
        assert hn._unwrap(bound) is base
        assert model_family(bound) == hn.OLLAMA
        assert hn._unwrap(base.with_retry()) is base

    def test_adapter_classes_are_resolved_once(self):
        assert hn._adapter_classes() is hn._adapter_classes()
