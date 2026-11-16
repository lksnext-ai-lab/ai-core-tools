"""Per-call chat history normaliser for conversations that switch models between turns.

The checkpoint stores every AIMessage exactly as the provider that wrote it produced it
(OpenAI Responses reasoning/function_call blocks, Anthropic thinking signatures, Gemini
thought signatures, ...). Another provider's LangChain converter either raises on those
(Ollama ``ValueError``, Google ``KeyError``) or forwards them to the wire (Mistral, Azure AI).

``HistoryNormalizerMiddleware`` rewrites the message list of ONE model call (through
``request.override``). It never writes to the agent state, so a later turn on the original
provider still sees the original blocks (OpenAI ``rs_``/``msg_`` item ids, Anthropic signatures).

- A message is the turn model's OWN (passes through untouched, same object) only when it has the
  same wire family AND the same stamp. The stamp (``response_metadata["aict_service_id"]`` /
  ``["aict_model"]``) is written to every answer this middleware sees come back from the model, so a
  message written by another AI service or another model of the same provider (reasoning items to a
  non-reasoning model, ``rs_``/``msg_`` ids of another project, Gemini thought signatures across
  models) counts as foreign. An unstamped message with list content / provider kwargs is foreign.
- A foreign AIMessage becomes plain text + the same tool calls (ids unchanged, so the
  ToolMessages that answer them stay paired) and keeps ``usage_metadata``.
- Optionally (``patch_interrupted_tool_calls``) a tool call without a ToolMessage gets a
  synthetic error ToolMessage in the view. Only the Chat enables it: a Chat turn can never
  pause for approval, so an unanswered call in its history is always an interrupted turn.
  Regular agents keep the existing recovery (agent_cache_service rollback).

Family detection reads the model class (never a user-controlled string) and, for OpenAI, whether
the Responses API is in use; the family of a stored message is read from the
``response_metadata`` its adapter wrote.
"""
from __future__ import annotations

import dataclasses
import functools
import logging
from typing import Any, Awaitable, Callable, Optional, Sequence

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ExtendedModelResponse
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from utils.logger import get_logger

logger = get_logger(__name__)

OPENAI_RESPONSES = "openai-responses"
OPENAI_CHAT = "openai-chat"
ANTHROPIC = "anthropic"
GOOGLE_GENAI = "google_genai"
MISTRALAI = "mistralai"
OLLAMA = "ollama"
AZURE_AI = "azure-ai"
BEDROCK = "bedrock"

# ``response_metadata["model_provider"]`` written by each adapter. OpenAI is split further
# (Responses vs Chat Completions) by ``_message_family``. Azure AI writes no tag at all.
_PROVIDER_TAG_FAMILY = {
    "anthropic": ANTHROPIC,
    "google_genai": GOOGLE_GENAI,
    "mistralai": MISTRALAI,
    "ollama": OLLAMA,
    "bedrock_converse": BEDROCK,
}

# Fallback on ``BaseChatModel._llm_type`` (class-defined, not user input) for wrappers/subclasses
# that are not instances of the adapter classes imported below.
_LLM_TYPE_FAMILY = {
    "anthropic-chat": ANTHROPIC,
    "mistralai-chat": MISTRALAI,
    "ollama-chat": OLLAMA,
    "chat-google-generative-ai": GOOGLE_GENAI,
    "google_genai": GOOGLE_GENAI,
    "amazon_bedrock_converse_chat": BEDROCK,
    "azure_ai_chat_completions_model": AZURE_AI,
}

STAMP_SERVICE_KEY = "aict_service_id"
STAMP_MODEL_KEY = "aict_model"

PLACEHOLDER_TEXT = "[no text response]"
INTERRUPTED_TOOL_TEXT = "Tool call interrupted: no result was recorded."


def _unwrap(model: Any) -> Any:
    seen = 0
    while hasattr(model, "bound") and seen < 5:  # RunnableBinding / retry wrappers
        model = model.bound
        seen += 1
    return model


def _openai_uses_responses(model: Any, tools: Sequence[Any]) -> bool:
    flag = getattr(model, "use_responses_api", None)
    if isinstance(flag, bool):
        return flag
    probe = {"tools": [t for t in tools if isinstance(t, dict)]}
    try:
        return bool(model._use_responses_api(probe))
    except Exception:  # private API: be conservative, assume Chat Completions
        return False


_ADAPTERS = (
    ("langchain_openai", "ChatOpenAI", OPENAI_CHAT),  # refined to Responses by ``model_family``
    ("langchain_anthropic", "ChatAnthropic", ANTHROPIC),
    ("langchain_mistralai", "ChatMistralAI", MISTRALAI),
    ("langchain_ollama", "ChatOllama", OLLAMA),
    ("langchain_google_genai", "ChatGoogleGenerativeAI", GOOGLE_GENAI),
    ("langchain_azure_ai.chat_models", "AzureAIChatCompletionsModel", AZURE_AI),
    ("langchain_aws", "ChatBedrockConverse", BEDROCK),
)


@functools.lru_cache(maxsize=1)
def _adapter_classes() -> tuple:
    """(class, family) of every installed adapter, resolved once; a broken import only drops its entry."""
    resolved = []
    for module, cls_name, family in _ADAPTERS:
        try:
            resolved.append((getattr(__import__(module, fromlist=[cls_name]), cls_name), family))
        except Exception:  # not installed / import-time failure of an optional provider
            continue
    return tuple(resolved)


def model_family(model: Any, tools: Sequence[Any] = ()) -> Optional[str]:
    """Wire family of the turn's model, from its class. None when it is not recognised."""
    model = _unwrap(model)
    for cls, family in _adapter_classes():
        if isinstance(model, cls):
            if family == OPENAI_CHAT and _openai_uses_responses(model, tools):
                return OPENAI_RESPONSES
            return family
    llm_type = getattr(model, "_llm_type", None)
    if llm_type == "openai-chat":
        return OPENAI_RESPONSES if _openai_uses_responses(model, tools) else OPENAI_CHAT
    return _LLM_TYPE_FAMILY.get(llm_type)


def _message_family(message: AIMessage) -> Optional[str]:
    """Family that wrote ``message``, from its ``response_metadata``; None when unknown."""
    metadata = message.response_metadata or {}
    tag = metadata.get("model_provider")
    if tag == "openai":
        if metadata.get("object") == "response" or isinstance(message.content, list):
            return OPENAI_RESPONSES
        return OPENAI_CHAT
    return _PROVIDER_TAG_FAMILY.get(tag)


def _is_plain(message: AIMessage) -> bool:
    """String content and nothing provider specific: every converter takes it as is."""
    return isinstance(message.content, str) and not message.additional_kwargs


def _stamp_of(message: AIMessage) -> tuple:
    metadata = message.response_metadata or {}
    return (metadata.get(STAMP_SERVICE_KEY), metadata.get(STAMP_MODEL_KEY))


def _is_foreign(message: AIMessage, turn_family: str, turn_stamp: Optional[tuple] = None) -> bool:
    if _is_plain(message):
        return False
    family = _message_family(message)
    if family is None or family != turn_family:
        # Unknown / missing tag (Azure AI, legacy rows) with list content or provider kwargs, or another provider.
        return True
    # Same wire family: only the same service AND model wrote it for sure (``None`` = stamp not known).
    return turn_stamp is not None and _stamp_of(message) != turn_stamp


def _text_of(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    parts = []
    for block in message.content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text") or "")
            elif block.get("type") == "refusal":
                parts.append(block.get("refusal") or block.get("text") or "")
    return "\n".join(p for p in parts if p)


def _to_plain(message: AIMessage) -> AIMessage:
    text = _text_of(message)
    if not text.strip() and not message.tool_calls and not message.invalid_tool_calls:
        # Reasoning-only answer: an empty non-final assistant turn is rejected (Anthropic).
        text = PLACEHOLDER_TEXT
    return AIMessage(
        content=text,
        tool_calls=[dict(tc) for tc in message.tool_calls],
        invalid_tool_calls=[dict(tc) for tc in message.invalid_tool_calls],
        id=message.id,
        name=message.name,
        usage_metadata=message.usage_metadata,
    )


def _patch_interrupted_tool_calls(messages: list[BaseMessage]) -> list[BaseMessage]:
    """After every AIMessage, add an error ToolMessage for each tool call the ToolMessages right after it
    (up to the next non-tool message) do not answer. Per message, not a global id set: ids can be reused."""
    out: list[BaseMessage] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        out.append(message)
        index += 1
        if not isinstance(message, AIMessage) or not message.tool_calls:
            continue
        answered = set()
        while index < len(messages) and isinstance(messages[index], ToolMessage):
            answered.add(messages[index].tool_call_id)
            out.append(messages[index])
            index += 1
        out.extend(
            ToolMessage(
                content=INTERRUPTED_TOOL_TEXT, tool_call_id=tc["id"], name=tc.get("name"), status="error",
            )
            for tc in message.tool_calls
            if tc.get("id") and tc["id"] not in answered
        )
    return out


def normalize_history(
    messages: Sequence[BaseMessage],
    turn_family: Optional[str],
    *,
    patch_interrupted_tool_calls: bool = False,
    turn_stamp: Optional[tuple] = None,
) -> list[BaseMessage]:
    """The history as the turn's model can take it. Returns a new list; never mutates inputs.

    ``turn_stamp`` is ``(service_id, model_name)`` of the turn; None skips the same-service check.
    """
    result: list[BaseMessage] = list(messages)
    rewritten = patched = 0
    if turn_family is not None:
        converted = []
        for m in result:
            if isinstance(m, AIMessage) and _is_foreign(m, turn_family, turn_stamp):
                converted.append(_to_plain(m))
                rewritten += 1
            else:
                converted.append(m)
        result = converted
    if patch_interrupted_tool_calls:
        before = len(result)
        result = _patch_interrupted_tool_calls(result)
        patched = len(result) - before
    # Numbers only (never message content).
    logger.log(
        logging.INFO if rewritten or patched else logging.DEBUG,
        "History normaliser: %d message(s) rewritten, %d tool result(s) patched", rewritten, patched,
    )
    return result


def _stamp_message(message: Any, stamp: dict) -> Any:
    if isinstance(message, AIMessage):
        return message.model_copy(update={"response_metadata": {**(message.response_metadata or {}), **stamp}})
    return message


def _stamp_response(response: Any, stamp: dict) -> Any:
    """Stamp the AIMessage(s) of what ``handler`` returned, on copies (the model's objects are not touched)."""
    if isinstance(response, ExtendedModelResponse):
        return dataclasses.replace(response, model_response=_stamp_response(response.model_response, stamp))
    if isinstance(response, ModelResponse):
        return dataclasses.replace(response, result=[_stamp_message(m, stamp) for m in response.result])
    return _stamp_message(response, stamp)


class HistoryNormalizerMiddleware(AgentMiddleware):
    """Rewrites the per-call message view for the model that serves the turn and stamps its answers.

    The view never reaches the state; the stamp does (it is part of the stored AIMessage on purpose).
    """

    def __init__(
        self,
        patch_interrupted_tool_calls: bool = False,
        service_id: Optional[int] = None,
        model_name: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.patch_interrupted_tool_calls = patch_interrupted_tool_calls
        self.service_id = service_id
        # Editing the service's model name later makes the older messages foreign (rewritten to plain text): harmless.
        self.model_name = model_name

    @property
    def _has_stamp(self) -> bool:
        return self.service_id is not None or self.model_name is not None

    def _view(self, request: ModelRequest) -> ModelRequest:
        try:
            family = model_family(request.model, request.tools)
            messages = normalize_history(
                request.messages,
                family,
                patch_interrupted_tool_calls=self.patch_interrupted_tool_calls,
                turn_stamp=(self.service_id, self.model_name) if self._has_stamp else None,
            )
            if len(messages) == len(request.messages) and all(a is b for a, b in zip(messages, request.messages)):
                return request
            return request.override(messages=messages)
        except Exception as exc:  # never break the turn because the view could not be built
            logger.warning("History normaliser skipped: %s", type(exc).__name__)
            return request

    def _stamped(self, response: Any) -> Any:
        if not self._has_stamp:
            return response
        try:
            return _stamp_response(response, {STAMP_SERVICE_KEY: self.service_id, STAMP_MODEL_KEY: self.model_name})
        except Exception as exc:
            logger.warning("History normaliser could not stamp the answer: %s", type(exc).__name__)
            return response

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        return self._stamped(handler(self._view(request)))

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
    ) -> ModelResponse:
        return self._stamped(await handler(self._view(request)))
