"""Provider-faithful fake chat models for the model-switch tests (app-flexible-chat step_012).

No provider is ever called. What is REAL and what is HAND-WRITTEN:

REAL (LangChain / provider-SDK code, offline):
  * the model object is a thin SUBCLASS of the real LangChain class the product builds in ``tools/aiServiceTools.py``
    (``ChatOpenAI(use_responses_api=True)``, ``ChatAnthropic``, ``ChatMistralAI``, ``AzureAIChatCompletionsModel``,
    ``ChatGoogleGenerativeAI``, ``ChatOllama`` for "Custom"), so ``isinstance`` / ``_llm_type`` / ``profile`` /
    ``_get_ls_params`` are the real ones and ``tools.middleware.history_normalizer.model_family`` detects the fake exactly
    as it detects the real class (asserted in ``TestSimulatorFidelity``). Only ``_generate`` / ``_stream`` (and their async
    twins) and ``bind_tools`` are replaced;
  * the REQUEST side: what a provider receives is run through that provider's own message converter
    (``ChatOpenAI._get_request_payload`` / ``ChatAnthropic._get_request_payload`` / ``ChatMistralAI._create_message_dicts``
    / ``langchain_azure_ai ... to_inference_message`` / ``ChatGoogleGenerativeAI._prepare_request`` /
    ``ChatOllama._chat_params``). Whatever the converter raises for a message list is what the fake raises;
  * the RESPONSE side: the AIMessage a provider "answers" is produced by the provider's own response parser from a
    canned raw response built with the provider SDK types (``ChatAnthropic._format_output`` on an ``anthropic.types.Message``,
    ``_construct_lc_result_from_responses_api`` on an ``openai.types.responses.Response``,
    ``ChatMistralAI._create_chat_result``, ``from_inference_message``, ``_response_to_result`` on a ``google.genai``
    response, ``_get_tool_calls_from_response`` of langchain_ollama), so content block shapes, ``additional_kwargs``,
    ``response_metadata``, tool-call ids and ``usage_metadata`` are the ones the adapters really produce.

HAND-WRITTEN (labelled ``sim rule`` / ``test_sim_rule_*`` in the tests):
  * canned raw payloads (texts, ids, token counts, reasoning text); Ollama's ``response_metadata`` (the real parser is
    inline in ``_iterate_over_stream``); the streaming chunking;
  * API-level invariants the converters do not check: ``check_tool_pairing`` (orphan tool call / tool message);
    ``check_mistral_payload`` and ``check_azure_payload`` (Mistral and Azure converters FORWARD foreign content blocks to
    the wire, so the fake checks the converter OUTPUT against the content-item types of the installed SDK models);
    ``check_ollama_images`` (Ollama ``images`` take base64 data, not URLs);
  * the capability / context-window rejections (no vision, no tool calling, context_length_exceeded) and the injected
    provider errors, emulated as ``ProviderRejected`` at CALL time (``_receive``), which is where real servers answer 4xx.

What "valid input for B" PROVES: B's own installed converter accepts the messages it was handed, the tool calls and tool
messages are paired, and (Mistral/Azure) the content blocks sent to the wire are item types of the SDK models.
What it does NOT prove (no real API is called): Anthropic validating the ``signature`` of replayed thinking blocks; OpenAI
Responses reasoning/output item pairing and rejection of foreign item ids; role alternation rules; real token accounting
(the summarization uses langchain's approximate counter and a per-test window); image size / mime limits; what a server does
with unknown extra keys.

SHAPES PRODUCTION PRODUCES TODAY (``backend/tools/aiServiceTools.py``): Anthropic is built WITHOUT ``thinking`` (no thinking
blocks, only text / tool_use); Google WITHOUT ``include_thoughts`` (no ``thought`` parts, but Gemini 2.5/3 still attach thought
signatures: ``extras.signature`` on text blocks and ``__gemini_function_call_thought_signatures__`` in additional_kwargs of
function-call messages); OpenAI through the Responses API when it has no custom endpoint (``reasoning`` / ``message`` /
``function_call`` blocks; reasoning models return ``reasoning`` items, here with the empty summary that is returned when none
is requested); Mistral / Azure / Custom (Ollama) return plain string content. ``reply(..., shape="today")`` builds those;
``shape="full"`` (the default, used by the unit tests) also builds shapes that are NOT produced today (Anthropic ``thinking``,
Google ``thinking`` blocks) because they are one config flag away.
"""
import base64
import copy
import itertools
import json
import re
import types
import warnings
from dataclasses import dataclass, field
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    ToolMessage,
)
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

PROVIDERS = ["OpenAI", "Anthropic", "MistralAI", "Azure", "Google", "Custom"]
# OpenAI: a reasoning-capable model (the product's regex ``_OPENAI_REASONING_MODEL`` matches ``gpt-5``), because the
# Responses API only returns ``reasoning`` items for those.
MODEL_NAMES = {
    "OpenAI": "gpt-5-mini", "Anthropic": "claude-sonnet-4-5", "MistralAI": "mistral-large-latest",
    "Azure": "azure-model", "Google": "gemini-2.5-flash", "Custom": "llama3",
}
# Providers with a reasoning / thinking shape in ``shape="full"`` (``reply`` default) ...
REASONING_PROVIDERS = {"OpenAI", "Anthropic", "Google"}
# ... and in ``shape="today"`` (what production's client configuration produces; Anthropic has no ``thinking`` enabled).
TODAY_REASONING_PROVIDERS = {"OpenAI", "Google"}
# Providers whose ``shape="full"`` reasoning shape is NOT produced by production today.
NOT_PRODUCED_TODAY = {"Anthropic", "Google"}  # ``thinking`` blocks (Anthropic ``thinking=``, Google ``include_thoughts``)

_SIGNATURE = base64.b64encode(bytes(range(64))).decode()  # a base64 string, like the real thinking signatures
_ids = itertools.count(1)


class ProviderRejected(Exception):
    """What the provider API / its LangChain converter would answer with a 4xx for the received messages."""


class ContextOverflow(ProviderRejected):
    """The provider's context_length_exceeded error."""


# ------------------------------------------------------------------ real model objects (offline)

_REAL: dict[str, Any] = {}


def _real_class(provider: str):
    if provider == "OpenAI":
        from langchain_openai import ChatOpenAI as cls
    elif provider == "Anthropic":
        from langchain_anthropic import ChatAnthropic as cls
    elif provider == "MistralAI":
        from langchain_mistralai import ChatMistralAI as cls
    elif provider == "Azure":
        from langchain_azure_ai.chat_models import AzureAIChatCompletionsModel as cls
    elif provider == "Google":
        from langchain_google_genai import ChatGoogleGenerativeAI as cls
    elif provider == "Custom":
        from langchain_ollama import ChatOllama as cls
    else:
        raise ValueError(provider)
    return cls


def _real_kwargs(provider: str) -> dict:
    """Constructor arguments as ``tools/aiServiceTools.py`` passes them (credentials replaced by dummies)."""
    name = MODEL_NAMES[provider]
    return {
        "OpenAI": {"model": name, "api_key": "x", "use_responses_api": True},  # prod: no endpoint => Responses API
        "Anthropic": {"model": name, "api_key": "x"},
        "MistralAI": {"model": name, "api_key": "x"},
        "Azure": {"model": name, "credential": "x", "endpoint": "https://example.invalid/models",
                  "api_version": "2024-05-01-preview"},
        "Google": {"model": name, "api_key": "x"},
        "Custom": {"model": name, "base_url": "http://example.invalid"},
    }[provider]


def real_model(provider: str):
    """The LangChain class the product would build for ``provider`` (no network access at construction)."""
    if provider not in _REAL:
        with warnings.catch_warnings():  # AzureAIChatCompletionsModel logs a "currently in preview" warning
            warnings.filterwarnings("ignore", message=".*is currently in preview.*")
            _REAL[provider] = _real_class(provider)(**_real_kwargs(provider))
    return _REAL[provider]


# ------------------------------------------------------------------ request side: validity for a provider


def check_tool_pairing(messages: list[BaseMessage]) -> None:
    """Sim rule (hand-written; the converters do not enforce it): no orphan tool call, no orphan tool message.

    OpenAI chat/Responses: "an assistant message with tool_calls must be followed by tool messages responding to each
    tool_call_id"; Anthropic: every ``tool_use`` needs its ``tool_result`` in the next user turn; Mistral/Azure/Ollama
    follow the OpenAI chat contract; Google needs the function response after the function call.
    The tool messages must directly follow their call.
    """
    pending: set[str] = set()
    for message in messages:
        if isinstance(message, ToolMessage):
            if message.tool_call_id not in pending:
                raise ProviderRejected(f"tool message {message.tool_call_id!r} answers no pending tool call")
            pending.discard(message.tool_call_id)
            continue
        if pending:
            raise ProviderRejected(f"tool call(s) {sorted(pending)} have no tool message before the next message")
        if isinstance(message, AIMessage) and message.tool_calls:
            pending = {tc["id"] for tc in message.tool_calls}
    if pending:
        raise ProviderRejected(f"orphan tool call(s) {sorted(pending)} at the end of the history")


# Azure AI Inference content items: azure/ai/inference/models/_models.py (azure-ai-inference 1.0.0b9)
#   AudioContentItem  line 54   (type "input_audio", field ``input_audio``)
#   ImageContentItem  line 992  (type "image_url",   field ``image_url``)
#   TextContentItem   line 1427 (type "text",        field ``text``)
AZURE_CONTENT_ITEMS = {
    "text": {"type", "text"},
    "image_url": {"type", "image_url"},
    "input_audio": {"type", "input_audio"},
}


def _mistral_content_chunks() -> dict[str, set[str]]:
    """Chunk type -> fields of the Mistral SDK ``ContentChunk`` union (mistralai/models/contentchunk.py:20-27:
    image_url, document_url, text, reference; fields from each chunk model, e.g. models/textchunk.py:17-20)."""
    import typing

    from mistralai.models.contentchunk import ContentChunk

    union = typing.get_args(ContentChunk)[0]
    chunks = {}
    for member in typing.get_args(union):
        cls, tag = typing.get_args(member)[0], typing.get_args(member)[1].tag
        chunks[tag] = set(cls.model_fields)
    return chunks


# Keys LangChain itself puts on content blocks (standard block id, streaming index): not SDK fields, tolerated (not proven).
LANGCHAIN_BOOKKEEPING_KEYS = {"id", "index"}


def _check_content_items(content: Any, allowed: dict[str, set[str]], who: str) -> None:
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            raise ProviderRejected(f"{who}: content item {type(block).__name__} is not an object")
        kind = block.get("type")
        if kind not in allowed:
            raise ProviderRejected(f"{who}: content item of unknown type {kind!r}")
        extra = set(block) - allowed[kind] - LANGCHAIN_BOOKKEEPING_KEYS
        if extra:
            raise ProviderRejected(f"{who}: content item {kind!r} with unknown key(s) {sorted(extra)}")


def check_mistral_payload(message_dicts: list[dict]) -> None:
    """Sim rule: the Mistral converter forwards list content untouched, so check what goes to the wire."""
    allowed = _mistral_content_chunks()
    for message in message_dicts:
        _check_content_items(message.get("content"), allowed, "Mistral")


def check_azure_payload(inference_messages: list) -> None:
    """Sim rule: the Azure converter forwards list content untouched, so check what goes to the wire."""
    for message in inference_messages:
        _check_content_items(dict(message).get("content"), AZURE_CONTENT_ITEMS, "Azure")


_BASE64 = re.compile(r"^[A-Za-z0-9+/=\s]*$")


def check_ollama_images(ollama_messages: list) -> None:
    """Sim rule: the Ollama chat API takes ``images`` as base64 data (API docs); a URL is not decodable."""
    for message in ollama_messages:
        for image in (message.get("images") if isinstance(message, dict) else getattr(message, "images", None)) or []:
            if not isinstance(image, str) or not _BASE64.match(image):
                raise ProviderRejected("Ollama: images must be base64 data, got a URL / non-base64 string")


def validate_for(provider: str, messages: list[BaseMessage]) -> None:
    """Raise what ``provider`` would raise for these messages: its converter's exception or a ProviderRejected."""
    check_tool_pairing(messages)
    payload = copy.deepcopy(messages)
    real = real_model(provider)
    if provider in ("OpenAI", "Anthropic"):
        real._get_request_payload(payload)
    elif provider == "MistralAI":
        check_mistral_payload(real._create_message_dicts(payload, None)[0])
    elif provider == "Azure":
        from langchain_azure_ai.chat_models.inference import to_inference_message

        check_azure_payload(to_inference_message(payload))
    elif provider == "Google":
        real._prepare_request(payload)
    elif provider == "Custom":
        check_ollama_images(real._chat_params(payload)["messages"])


# ------------------------------------------------------------------ response side: what a provider produces


def reply(
    provider: str, text: str, tool_call: Optional[tuple[str, dict]] = None, reasoning: bool = True, shape: str = "full",
) -> AIMessage:
    """The AIMessage ``provider``'s adapter produces for a canned raw answer (text, optionally one tool call).

    ``shape="full"``: reasoning means OpenAI ``reasoning`` item with summary, Anthropic ``thinking`` block, Google ``thinking``
    block (shapes that are not all produced today). ``shape="today"``: only what production's client configuration
    produces (see the module docstring): no Anthropic thinking, Google thought signatures instead of thinking blocks.
    """
    assert shape in ("full", "today"), shape
    n = next(_ids)
    reasoning = reasoning and provider in (TODAY_REASONING_PROVIDERS if shape == "today" else REASONING_PROVIDERS)
    return _BUILDERS[provider](n, text, tool_call, reasoning, shape)


def has_reasoning_shape(provider: str, shape: str) -> bool:
    return provider in (TODAY_REASONING_PROVIDERS if shape == "today" else REASONING_PROVIDERS)


def _anthropic(n, text, tool_call, reasoning, shape):
    from anthropic.types import Message, TextBlock, ThinkingBlock, ToolUseBlock, Usage

    content = []
    if reasoning:
        content.append(ThinkingBlock(type="thinking", thinking=f"thinking {n}", signature=_SIGNATURE))
    if text:
        content.append(TextBlock(type="text", text=text))
    if tool_call:
        content.append(ToolUseBlock(type="tool_use", id=f"toolu_01{n:022d}", name=tool_call[0], input=tool_call[1]))
    raw = Message(
        id=f"msg_01{n:022d}", type="message", role="assistant", model=MODEL_NAMES["Anthropic"], content=content,
        stop_reason="tool_use" if tool_call else "end_turn", stop_sequence=None, usage=Usage(input_tokens=11, output_tokens=7),
    )
    message = real_model("Anthropic")._format_output(raw).generations[0].message
    message.id = raw.id
    return message


def _openai(n, text, tool_call, reasoning, shape):
    from langchain_openai.chat_models.base import _construct_lc_result_from_responses_api
    from openai.types.responses import (
        Response, ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText, ResponseReasoningItem,
        ResponseUsage,
    )
    from openai.types.responses.response_reasoning_item import Summary
    from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

    output = []
    if reasoning:
        summary = [] if shape == "today" else [Summary(type="summary_text", text=f"thinking {n}")]  # none is requested today
        output.append(ResponseReasoningItem(id=f"rs_{n:016d}", type="reasoning", summary=summary))
    if text:
        output.append(ResponseOutputMessage(
            id=f"msg_{n:016d}", type="message", role="assistant", status="completed",
            content=[ResponseOutputText(type="output_text", text=text, annotations=[])]))
    if tool_call:
        output.append(ResponseFunctionToolCall(
            id=f"fc_{n:016d}", type="function_call", call_id=f"call_{n:016d}", name=tool_call[0],
            arguments=json.dumps(tool_call[1]), status="completed"))
    raw = Response(
        id=f"resp_{n:016d}", created_at=1.0, model=MODEL_NAMES["OpenAI"], object="response", parallel_tool_calls=True,
        tool_choice="auto", tools=[], output=output, status="completed",
        usage=ResponseUsage(
            input_tokens=11, output_tokens=7, total_tokens=18,
            input_tokens_details=InputTokensDetails(cached_tokens=0, cache_write_tokens=0),
            output_tokens_details=OutputTokensDetails(reasoning_tokens=3 if reasoning else 0)),
    )
    return _construct_lc_result_from_responses_api(raw).generations[0].message


def _mistral(n, text, tool_call, reasoning, shape):
    message: dict[str, Any] = {"role": "assistant", "content": text}
    if tool_call:
        message["tool_calls"] = [{"id": f"mT{n:07d}"[:9], "function": {"name": tool_call[0], "arguments": json.dumps(tool_call[1])}}]
    raw = {
        "id": f"cmpl-{n}", "model": MODEL_NAMES["MistralAI"], "created": 1,
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if tool_call else "stop"}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }
    return real_model("MistralAI")._create_chat_result(raw).generations[0].message


def _azure(n, text, tool_call, reasoning, shape):
    from azure.ai.inference.models import ChatResponseMessage
    from langchain_azure_ai.chat_models.inference import from_inference_message

    raw: dict[str, Any] = {"role": "assistant", "content": text}
    if tool_call:
        raw["tool_calls"] = [{
            "id": f"call_az{n:010d}", "type": "function",
            "function": {"name": tool_call[0], "arguments": json.dumps(tool_call[1])}}]
    return from_inference_message(ChatResponseMessage(raw))


def _google(n, text, tool_call, reasoning, shape):
    from google.genai import types as gt
    from langchain_google_genai.chat_models import _response_to_result

    signature = bytes(range(64))
    parts = []
    if reasoning and shape == "full":  # ``include_thoughts``: NOT produced today
        parts.append(gt.Part(text=f"thinking {n}", thought=True, thought_signature=signature))
    if text:
        # today: a Gemini 2.5/3 text part carries a thought signature without any ``thought`` part
        parts.append(gt.Part(text=text, thought_signature=signature if reasoning and shape == "today" else None))
    if tool_call:
        parts.append(gt.Part(
            function_call=gt.FunctionCall(name=tool_call[0], args=tool_call[1]),
            thought_signature=signature if reasoning and shape == "today" else None))
    raw = gt.GenerateContentResponse(
        candidates=[gt.Candidate(content=gt.Content(role="model", parts=parts), finish_reason="STOP")],
        usage_metadata=gt.GenerateContentResponseUsageMetadata(
            prompt_token_count=11, candidates_token_count=7, total_token_count=18),
        model_version=MODEL_NAMES["Google"],
    )
    return _response_to_result(raw).generations[0].message


def _ollama(n, text, tool_call, reasoning, shape):
    from langchain_ollama.chat_models import _get_tool_calls_from_response

    response = {"message": {"tool_calls": [{"function": {"name": tool_call[0], "arguments": tool_call[1]}}]}} if tool_call else {}
    return AIMessage(
        content=text,
        tool_calls=_get_tool_calls_from_response(response),
        response_metadata={
            "model": MODEL_NAMES["Custom"], "created_at": "2025-01-01T00:00:00Z", "done": True, "done_reason": "stop",
            "total_duration": 1000, "load_duration": 10, "prompt_eval_count": 11, "prompt_eval_duration": 100,
            "eval_count": 7, "eval_duration": 100, "model_name": MODEL_NAMES["Custom"], "model_provider": "ollama",
        },
        usage_metadata={"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
    )


_BUILDERS = {
    "OpenAI": _openai, "Anthropic": _anthropic, "MistralAI": _mistral, "Azure": _azure, "Google": _google,
    "Custom": _ollama,
}


def has_image_block(message: BaseMessage) -> bool:
    return isinstance(message.content, list) and any(
        isinstance(b, dict) and b.get("type") in ("image_url", "image") for b in message.content
    )


# ------------------------------------------------------------------ the recording model


@dataclass
class Call:
    service_id: int
    provider: str
    messages: list  # deep copy of what the model received
    is_summary: bool
    bound_tools: list
    tokens: int  # approximate token count of ``messages``
    answer: Any = None  # the AIMessage this call produced (before any streaming merge)


@dataclass
class Sim:
    """Per-test control panel of the simulated models (plus the ids the ``sim`` fixture of the tests fills in)."""

    provider_of: dict = field(default_factory=dict)  # service_id -> provider
    calls: list = field(default_factory=list)
    windows: dict = field(default_factory=dict)  # service_id -> max_input_tokens (None: model without profile)
    enforce_window: set = field(default_factory=set)  # service ids that reject an input above their window
    no_vision: set = field(default_factory=set)  # reject image blocks at call time
    no_tools: set = field(default_factory=set)  # reject a call that has tools bound, at CALL time (real Ollama / Azure)
    no_tools_at_bind: set = field(default_factory=set)  # bind_tools itself raises NotImplementedError (not what real ones do)
    call_tool: dict = field(default_factory=dict)  # service_id -> tool name to call when it is bound
    reasoning: bool = True
    shape: str = "today"  # reply() shape: what production produces today
    fail_summary: set = field(default_factory=set)  # service ids whose summary call raises an injected provider error
    summary_status: dict = field(default_factory=dict)  # service_id -> ``status_code`` carried by that injected error
    fail_main: set = field(default_factory=set)  # service ids whose main call raises an injected provider error
    fail_after_chunks: dict = field(default_factory=dict)  # service_id -> chunks streamed before the stream breaks
    rejections: list = field(default_factory=list)  # (service_id, "ExcType: message") of every raised error
    bind_attempts: list = field(default_factory=list)  # (service_id, tool names) of every bind_tools call
    ids: dict = field(default_factory=dict)  # provider -> service_id
    silo: Optional[int] = None
    silo2: Optional[int] = None
    retriever: str = ""
    retriever2: str = ""
    after_first: int = 0  # number of model calls made by turn 1

    def of(self, service_id: int) -> list:
        return [c for c in self.calls if c.service_id == service_id]

    def main_calls(self, service_id: int) -> list:
        return [c for c in self.of(service_id) if not c.is_summary]

    def summary_calls(self, service_id: Optional[int] = None) -> list:
        return [c for c in self.calls if c.is_summary and (service_id is None or c.service_id == service_id)]


SUMMARY_MARKER = "Context Extraction Assistant"


def summary_text(service_id: int) -> str:
    return f"SUMMARY-WRITTEN-BY-{service_id}"


class _SimBehaviour:
    """Mixin replacing the network methods of a real LangChain chat-model class."""

    # fields (declared on the generated subclass): service_id, sim_provider, sim, bound_names

    def _answer(self, messages) -> AIMessage:
        sim: Sim = self.sim
        first = messages[0] if messages else None
        if len(messages) == 1 and SUMMARY_MARKER in (first.text or ""):
            return reply(self.sim_provider, summary_text(self.service_id), reasoning=False, shape=sim.shape)
        tool = sim.call_tool.get(self.service_id)
        last_human = max((i for i, m in enumerate(messages) if m.type == "human"), default=-1)
        answered = any(isinstance(m, ToolMessage) for m in messages[last_human + 1:])
        if tool and tool in self.bound_names and not answered:
            return reply(self.sim_provider, "", (tool, {"query": "q"}), reasoning=sim.reasoning, shape=sim.shape)
        return reply(self.sim_provider, f"hello from {self.service_id}", reasoning=sim.reasoning, shape=sim.shape)

    def _fail(self, exc: Exception):
        self.sim.rejections.append((self.service_id, f"{type(exc).__name__}: {exc}"))
        raise exc

    def _receive(self, messages) -> Call:
        sim: Sim = self.sim
        is_summary = len(messages) == 1 and SUMMARY_MARKER in (messages[0].text or "")
        tokens = count_tokens_approximately(messages)
        window = sim.windows.get(self.service_id)
        call = Call(self.service_id, self.sim_provider, copy.deepcopy(list(messages)), is_summary,
                    list(self.bound_names), tokens)
        sim.calls.append(call)
        try:
            if is_summary and self.service_id in sim.fail_summary:
                error = ProviderRejected("injected provider error (summary call)")
                if self.service_id in sim.summary_status:
                    error.status_code = sim.summary_status[self.service_id]  # what the SDK errors carry (400, 429 ...)
                raise error
            if not is_summary and self.service_id in sim.fail_main:
                raise ProviderRejected("injected provider error (main call)")
            if self.service_id in sim.enforce_window and window and tokens > window:
                raise ContextOverflow(f"context_length_exceeded: {tokens} tokens > {window}")
            if self.service_id in sim.no_vision and any(has_image_block(m) for m in messages):
                raise ProviderRejected("this model does not accept image input")
            if self.service_id in sim.no_tools and self.bound_names:
                raise ProviderRejected("this model does not support tool calling")  # HTTP 400 of the server, at call time
            validate_for(self.sim_provider, list(messages))
        except Exception as exc:  # a converter's own exception (KeyError, ValueError...) or ProviderRejected
            sim.rejections.append((self.service_id, f"{type(exc).__name__}: {exc}"))
            raise
        return call

    # -- BaseChatModel API
    def bind_tools(self, tools, **kwargs):
        names = [getattr(t, "name", None) or t.get("name") or t["function"]["name"] for t in tools]
        self.sim.bind_attempts.append((self.service_id, names))
        if self.service_id in self.sim.no_tools_at_bind:
            raise NotImplementedError("this model does not support tool calling")
        # Like a real bind: a new runnable, the unbound model (used by the summarization) is not changed.
        return self.model_copy(update={"bound_names": names})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        call = self._receive(messages)
        call.answer = self._answer(messages)
        return ChatResult(generations=[ChatGeneration(message=call.answer)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return await BaseChatModel._agenerate(self, messages, stop, run_manager, **kwargs)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        async for chunk in BaseChatModel._astream(self, messages, stop, run_manager, **kwargs):
            yield chunk

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        call = self._receive(messages)
        message = call.answer = self._answer(messages)
        text_blocks = isinstance(message.content, list) and [b for b in message.content if b.get("type") == "text"]
        if message.tool_calls or (isinstance(message.content, list) and len(message.content) != len(text_blocks)):
            chunk = AIMessageChunk(
                content=message.content, id=message.id, response_metadata=message.response_metadata,
                usage_metadata=message.usage_metadata, additional_kwargs=message.additional_kwargs,
                tool_call_chunks=[
                    {"name": tc["name"], "args": json.dumps(tc["args"]), "id": tc["id"], "index": i}
                    for i, tc in enumerate(message.tool_calls)
                ],
            )
            yield ChatGenerationChunk(message=chunk)
            return
        words = message.text.split(" ")
        limit = self.sim.fail_after_chunks.get(self.service_id)
        for index, word in enumerate(words):
            if limit is not None and index >= limit:
                self._fail(ConnectionError(f"injected provider error: the stream broke after {index} chunk(s)"))
            piece = word if index == 0 else f" {word}"
            content = [{"type": "text", "text": piece, "index": 0}] if isinstance(message.content, list) else piece
            last = index == len(words) - 1
            chunk = AIMessageChunk(
                content=content, id=message.id if index == 0 else None,
                response_metadata=message.response_metadata if last else {},
                usage_metadata=message.usage_metadata if last else None,
            )
            if run_manager:
                run_manager.on_llm_new_token(chunk.text, chunk=ChatGenerationChunk(message=chunk))
            yield ChatGenerationChunk(message=chunk)


_SIM_CLASSES: dict[tuple, type] = {}


def sim_class(provider: str):
    """``Sim<RealClass>``: a subclass of the product's real class with the network methods replaced."""
    if provider not in _SIM_CLASSES:
        real_cls = _real_class(provider)

        def body(ns):
            ns["__annotations__"] = {"service_id": int, "sim_provider": str, "sim": Any, "bound_names": list}
            ns["bound_names"] = []

        _SIM_CLASSES[provider] = types.new_class(f"Sim{real_cls.__name__}", (_SimBehaviour, real_cls), {}, body)
    return _SIM_CLASSES[provider]


def SimChatModel(service_id: int, provider: str, sim: Sim, profile: Any = None, **overrides):  # noqa: N802
    """An instance of the real class' subclass, built with the product's constructor arguments (dummy credentials).

    ``profile=None`` keeps the real class' own profile; ``{}`` means "no profile" (the factory then falls back to 32k).
    """
    kwargs = {**_real_kwargs(provider), **overrides}
    if profile is not None:
        kwargs["profile"] = profile
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*is currently in preview.*")
        return sim_class(provider)(service_id=service_id, sim_provider=provider, sim=sim, **kwargs)
