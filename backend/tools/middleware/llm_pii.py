"""LLM-based PII detection middleware — additive to the regex-based PIIMiddleware.

Unlike LangChain's built-in ``PIIMiddleware``, this uses an LLM call to find PII
that doesn't follow a fixed pattern (names, addresses, custom entity types).
This needs its own async hooks: LangChain's built-in ``PIIMiddleware.detector``
param is a synchronous callable only (``abefore_model`` just calls the sync
``before_model`` directly), so an LLM call — a network request — can't be driven
through it without blocking the event loop this app's agents run on.
"""
from __future__ import annotations

import re

from langchain.agents.middleware._redaction import PIIMatch, apply_strategy
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from utils.logger import get_logger

logger = get_logger(__name__)


class _PIIFinding(BaseModel):
    type: str
    value: str


class _PIIDetectionResult(BaseModel):
    findings: list[_PIIFinding]


_DETECTION_PROMPT_TEMPLATE = (
    "You are a PII detection engine. Scan the TEXT below and find every instance "
    "of these entity types: {entities}.\n\n"
    "Return only entities that literally appear in the text — do not paraphrase, "
    "normalize, or translate the value; return the exact substring as it appears. "
    "If none are found, return an empty list.\n\n"
    "TEXT:\n\"\"\"\n{content}\n\"\"\""
)


def _build_matches(content: str, findings: list[_PIIFinding]) -> list[PIIMatch]:
    matches: list[PIIMatch] = []
    for finding in findings:
        if not finding.value:
            continue
        pattern = re.compile(re.escape(finding.value), re.IGNORECASE)
        found_any = False
        for m in pattern.finditer(content):
            found_any = True
            matches.append(PIIMatch(type=finding.type, value=m.group(), start=m.start(), end=m.end()))
        if not found_any:
            logger.warning(
                f"[LLMPIIMiddleware] LLM-reported value not found verbatim in content, "
                f"skipped: type={finding.type!r}"
            )
    return matches


class LLMPIIMiddleware(AgentMiddleware):
    """Detect PII using an LLM, in addition to (not instead of) regex detection.

    Runs alongside the built-in ``PIIMiddleware`` instances built from the
    regex ``pii_types`` selection — this middleware only adds a second,
    LLM-driven detection pass over the same messages.
    """

    def __init__(
        self,
        llm,
        entities: list[str],
        strategy: str = "redact",
        apply_to_input: bool = True,
        apply_to_output: bool = True,
        apply_to_tool_results: bool = True,
    ) -> None:
        super().__init__()
        self.entities = entities
        self.strategy = strategy
        self.apply_to_input = apply_to_input
        self.apply_to_output = apply_to_output
        self.apply_to_tool_results = apply_to_tool_results
        self._structured_llm = llm.with_structured_output(_PIIDetectionResult)

    @property
    def name(self) -> str:
        return f"{self.__class__.__name__}[{','.join(self.entities)}]"

    async def _detect(self, content: str) -> list[PIIMatch]:
        if not content or not self.entities:
            return []
        prompt = _DETECTION_PROMPT_TEMPLATE.format(entities=", ".join(self.entities), content=content)
        # Tag this call as middleware-internal, same convention LangChain's own
        # SummarizationMiddleware uses, so tools/streaming_utils.py suppresses
        # it from the user-facing SSE token stream instead of leaking the raw
        # structured-output JSON into the chat response.
        result = await self._structured_llm.ainvoke(prompt, config={"metadata": {"lc_source": "pii"}})
        return _build_matches(content, result.findings)

    async def _process_content(self, content: str) -> tuple[str, list[PIIMatch]]:
        matches = await self._detect(content)
        if not matches:
            return content, []
        sanitized = apply_strategy(content, matches, self.strategy)
        return sanitized, matches

    async def abefore_model(self, state, runtime) -> dict | None:
        """Check user input and tool results for PII before the model is called."""
        if not self.apply_to_input and not self.apply_to_tool_results:
            return None

        messages = state["messages"]
        if not messages:
            return None

        new_messages = list(messages)
        any_modified = False

        if self.apply_to_input:
            last_user_msg = None
            last_user_idx = None
            for i in range(len(messages) - 1, -1, -1):
                if isinstance(messages[i], HumanMessage):
                    last_user_msg = messages[i]
                    last_user_idx = i
                    break

            if last_user_idx is not None and last_user_msg and last_user_msg.content:
                content = str(last_user_msg.content)
                new_content, matches = await self._process_content(content)
                if matches:
                    new_messages[last_user_idx] = HumanMessage(
                        content=new_content, id=last_user_msg.id, name=last_user_msg.name,
                    )
                    any_modified = True

        if self.apply_to_tool_results:
            last_ai_idx = None
            for i in range(len(messages) - 1, -1, -1):
                if isinstance(messages[i], AIMessage):
                    last_ai_idx = i
                    break

            if last_ai_idx is not None:
                for i in range(last_ai_idx + 1, len(messages)):
                    msg = messages[i]
                    if isinstance(msg, ToolMessage) and msg.content:
                        content = str(msg.content)
                        new_content, matches = await self._process_content(content)
                        if matches:
                            new_messages[i] = ToolMessage(
                                content=new_content, id=msg.id, name=msg.name, tool_call_id=msg.tool_call_id,
                            )
                            any_modified = True

        if any_modified:
            return {"messages": new_messages}
        return None

    async def aafter_model(self, state, runtime) -> dict | None:
        """Check the AI's response for PII after the model is called."""
        if not self.apply_to_output:
            return None

        messages = state["messages"]
        if not messages:
            return None

        last_ai_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], AIMessage):
                last_ai_idx = i
                break

        if last_ai_idx is None:
            return None

        ai_msg = messages[last_ai_idx]
        if not ai_msg.content:
            return None

        content = str(ai_msg.content)
        new_content, matches = await self._process_content(content)
        if not matches:
            return None

        new_messages = list(messages)
        new_messages[last_ai_idx] = AIMessage(
            content=new_content, id=ai_msg.id, name=ai_msg.name, tool_calls=ai_msg.tool_calls,
        )
        return {"messages": new_messages}
