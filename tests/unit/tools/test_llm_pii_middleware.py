"""Unit tests for LLMPIIMiddleware (LLM-based PII detection, additive to regex)."""
import pytest

from langchain.agents.middleware._redaction import PIIDetectionError
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tools.middleware.llm_pii import LLMPIIMiddleware, _PIIDetectionResult, _PIIFinding


class _FakeStructuredLLM:
    def __init__(self, findings):
        self._findings = findings
        self.last_config = None

    async def ainvoke(self, prompt, config=None):
        self.last_config = config
        return _PIIDetectionResult(findings=self._findings)


class _FakeLLM:
    def __init__(self, findings):
        self._findings = findings
        self.structured_llm = None

    def with_structured_output(self, schema):
        self.structured_llm = _FakeStructuredLLM(self._findings)
        return self.structured_llm


class _FakeRuntime:
    pass


@pytest.mark.asyncio
async def test_redacts_detected_entity_in_input():
    llm = _FakeLLM([_PIIFinding(type="person", value="John Smith")])
    mw = LLMPIIMiddleware(llm=llm, entities=["person"], strategy="redact")
    state = {"messages": [HumanMessage(content="My name is John Smith.")]}

    result = await mw.abefore_model(state, _FakeRuntime())

    assert result is not None
    assert result["messages"][0].content == "My name is [REDACTED_PERSON]."


@pytest.mark.asyncio
async def test_no_findings_returns_none():
    llm = _FakeLLM([])
    mw = LLMPIIMiddleware(llm=llm, entities=["person"], strategy="redact")
    state = {"messages": [HumanMessage(content="Nothing sensitive here.")]}

    result = await mw.abefore_model(state, _FakeRuntime())

    assert result is None


@pytest.mark.asyncio
async def test_value_not_found_verbatim_is_skipped_not_raised():
    llm = _FakeLLM([_PIIFinding(type="person", value="Jonathan Smithsonian")])
    mw = LLMPIIMiddleware(llm=llm, entities=["person"], strategy="redact")
    state = {"messages": [HumanMessage(content="My name is John Smith.")]}

    result = await mw.abefore_model(state, _FakeRuntime())

    assert result is None


@pytest.mark.asyncio
async def test_block_strategy_raises_on_match():
    llm = _FakeLLM([_PIIFinding(type="person", value="John Smith")])
    mw = LLMPIIMiddleware(llm=llm, entities=["person"], strategy="block")
    state = {"messages": [HumanMessage(content="My name is John Smith.")]}

    with pytest.raises(PIIDetectionError):
        await mw.abefore_model(state, _FakeRuntime())


@pytest.mark.asyncio
async def test_apply_to_output_redacts_ai_message():
    llm = _FakeLLM([_PIIFinding(type="email", value="jane@example.com")])
    mw = LLMPIIMiddleware(llm=llm, entities=["email"], strategy="mask", apply_to_output=True)
    state = {"messages": [AIMessage(content="Contact jane@example.com for details.")]}

    result = await mw.aafter_model(state, _FakeRuntime())

    assert result is not None
    assert "jane@example.com" not in result["messages"][0].content


@pytest.mark.asyncio
async def test_apply_to_tool_results_redacts_tool_message():
    llm = _FakeLLM([_PIIFinding(type="ip", value="10.0.0.5")])
    mw = LLMPIIMiddleware(
        llm=llm, entities=["ip"], strategy="hash",
        apply_to_input=False, apply_to_tool_results=True,
    )
    state = {
        "messages": [
            AIMessage(content="calling tool", tool_calls=[]),
            ToolMessage(content="Server at 10.0.0.5 responded", tool_call_id="call_1"),
        ]
    }

    result = await mw.abefore_model(state, _FakeRuntime())

    assert result is not None
    assert "10.0.0.5" not in result["messages"][1].content


@pytest.mark.asyncio
async def test_detector_call_tagged_with_lc_source_pii():
    # The streaming layer (tools/streaming_utils.py) only suppresses
    # middleware-internal LLM calls that are tagged via
    # config={"metadata": {"lc_source": ...}} — untagged calls leak their raw
    # output into the user-facing SSE token stream. Regression test for that.
    llm = _FakeLLM([_PIIFinding(type="person", value="John Smith")])
    mw = LLMPIIMiddleware(llm=llm, entities=["person"], strategy="redact")
    state = {"messages": [HumanMessage(content="My name is John Smith.")]}

    await mw.abefore_model(state, _FakeRuntime())

    assert llm.structured_llm.last_config == {"metadata": {"lc_source": "pii"}}


@pytest.mark.asyncio
async def test_empty_entities_list_skips_detection_entirely():
    llm = _FakeLLM([_PIIFinding(type="person", value="John Smith")])
    mw = LLMPIIMiddleware(llm=llm, entities=[], strategy="redact")
    state = {"messages": [HumanMessage(content="My name is John Smith.")]}

    result = await mw.abefore_model(state, _FakeRuntime())

    assert result is None
