"""Runtime enforcement of retired AI services (step_004 of service-end-of-service).

No network: provider builders and DB access are patched.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents import create_agent as create_langchain_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from models.agent import Agent
from models.ai_service import AIService
from tools import agentTools
from utils.service_lifecycle import ServiceRetiredError

PAST = datetime.now(timezone.utc) - timedelta(days=3)
FUTURE = datetime.now(timezone.utc) + timedelta(days=30)


def _svc(eos, provider="OpenAI", **extra):
    return SimpleNamespace(
        service_id=7, app_id=3, name="gpt-old", end_of_service_at=eos, deprecation_notice="Use gpt-new.",
        provider=provider, description="m", api_key="k", endpoint=None, supports_video=True, **extra,
    )


@pytest.fixture
def lifecycle_caplog(caplog):
    from utils import service_lifecycle

    service_lifecycle.logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG)
    yield caplog
    service_lifecycle.logger.removeHandler(caplog.handler)


def _warnings(caplog):
    return [r for r in caplog.records if r.levelno >= logging.WARNING and "service_lifecycle.blocked" in r.getMessage()]


# --- create_llm_from_service / get_embedding -------------------------------------------


def test_create_llm_retired_raises_without_calling_provider(lifecycle_caplog):
    from tools import aiServiceTools

    with patch.object(aiServiceTools, "_build_openai_llm") as builder:
        with pytest.raises(ServiceRetiredError) as ei:
            aiServiceTools.create_llm_from_service(_svc(PAST))
    builder.assert_not_called()
    assert "Use gpt-new." in ei.value.message
    assert len(_warnings(lifecycle_caplog)) == 1


@pytest.mark.parametrize("eos", [FUTURE, None])
def test_create_llm_active_builds(eos):
    from tools import aiServiceTools

    with patch.object(aiServiceTools, "_build_openai_llm", return_value="LLM") as builder:
        assert aiServiceTools.create_llm_from_service(_svc(eos)) == "LLM"
    builder.assert_called_once()


def test_create_llm_mock_service_without_lifecycle_attrs_still_works():
    from tools import aiServiceTools

    mock = SimpleNamespace(provider="OpenAI", description="m", api_key="k", endpoint=None)
    with patch.object(aiServiceTools, "_build_openai_llm", return_value="LLM"):
        assert aiServiceTools.create_llm_from_service(mock) == "LLM"


def test_get_embedding_retired_raises():
    from tools import aiServiceTools

    with patch.object(aiServiceTools, "get_embeddings_model") as model:
        with pytest.raises(ServiceRetiredError):
            aiServiceTools.get_embedding("hi", _svc(PAST))
    model.assert_not_called()


def test_middleware_resolve_llm_retired_raises():
    from tools.middleware.factory import _resolve_llm

    agent = SimpleNamespace(agent_id=1, app=SimpleNamespace(ai_services=[_svc(PAST)]))
    with pytest.raises(ServiceRetiredError):
        _resolve_llm(agent, "ai_service:7", default_llm=object())


def test_ocr_vision_get_llm_retired_raises():
    from tools.aiServiceTools import get_llm

    agent = SimpleNamespace(vision_service_rel=_svc(PAST), ai_service=None, temperature=0)
    with pytest.raises(ServiceRetiredError):
        get_llm(agent, is_vision=True)


# --- transcription / video --------------------------------------------------------------


def test_transcription_retired_raises():
    from tools import transcriptionTools

    with patch.object(transcriptionTools, "transcribe_with_openai_whisper") as t:
        with pytest.raises(ServiceRetiredError):
            transcriptionTools.get_transcription_from_service(_svc(PAST), "/tmp/x.wav")
    t.assert_not_called()


def test_video_analysis_retired_raises():
    from services import video_analysis_service as vas

    with patch.object(vas.AIServiceRepository, "get_by_id", return_value=_svc(PAST, provider="Google")):
        with pytest.raises(ServiceRetiredError):
            vas.VideoAnalysisService.analyze_video("/tmp/none.mp4", 7, MagicMock())


# --- agent-as-tool (AD-7) ---------------------------------------------------------------


def _tool_agent(eos):
    agent = Agent(name="Sub", description="d", system_prompt="")
    agent.ai_service = AIService(name="gpt-old", provider="OpenAI", description="m", api_key="k")
    agent.ai_service.end_of_service_at = eos
    agent.ai_service.service_id = 7
    return agent


@pytest.mark.asyncio
async def test_iact_tool_constructs_with_retired_llm_and_fails_only_on_invocation(lifecycle_caplog):
    from tools import aiServiceTools

    agent = _tool_agent(PAST)
    with patch.object(aiServiceTools, "_build_openai_llm") as builder, \
         patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)):
        tool_ = await agentTools.IACTTool.create(agent)  # parent build must not fail
        assert len(_warnings(lifecycle_caplog)) == 1  # logged once, at build time
        with pytest.raises(ServiceRetiredError):
            await tool_._arun("hello")
        with pytest.raises(ServiceRetiredError):
            tool_._run("hello")
    builder.assert_not_called()
    assert len(_warnings(lifecycle_caplog)) == 1  # re-raising the stored error does not log again


def test_iact_tool_without_ai_service_still_raises_at_init():
    agent = Agent(name="Sub", description="d", system_prompt="")
    with pytest.raises(ValueError, match="No LLM found"):
        agentTools.IACTTool(agent)


@pytest.mark.asyncio
async def test_iact_ocr_tool_defers_retired_llm():
    from tools import aiServiceTools

    agent = _tool_agent(PAST)
    with patch.object(aiServiceTools, "_build_openai_llm") as builder:
        tool_ = await agentTools.IACTOCRTool.create(agent)
        with pytest.raises(ServiceRetiredError):
            await tool_._arun("hello")
    builder.assert_not_called()


# --- retriever tool ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retriever_search_propagates_service_retired():
    silo = SimpleNamespace(
        silo_id=5, name="s", description="d", metadata_definition=None, metadata_definition_id=None,
        vector_db_type="PGVECTOR", app_id=1,
    )
    retired = ServiceRetiredError(_svc(PAST), "embedding")
    with patch.object(agentTools, "_run_retrieval", new=AsyncMock(side_effect=retired)), \
         patch.object(agentTools, "MetadataValuesCacheService", create=True), \
         patch.object(agentTools, "SessionLocal", MagicMock()):
        search_tool = agentTools.get_retriever_tool(silo=silo)
        with pytest.raises(ServiceRetiredError):
            await search_tool.coroutine(query="q")


# --- LangGraph ToolNode / create_agent propagation --------------------------------------


class _ToolCallingModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "fake-tool-caller"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        msg = AIMessage(content="", tool_calls=[{"name": "boom", "args": {}, "id": "c1"}])
        return ChatResult(generations=[ChatGeneration(message=msg)])


@pytest.mark.asyncio
async def test_agent_chain_propagates_service_retired_from_tool():
    """ToolNode's default error handling only swallows ToolInvocationError; the rest propagates."""

    @tool
    async def boom() -> str:
        """Always fails with a retired service."""
        raise ServiceRetiredError(_svc(PAST), "embedding")

    chain = create_langchain_agent(model=_ToolCallingModel(), tools=[boom])
    with pytest.raises(ServiceRetiredError) as ei:
        await chain.ainvoke({"messages": [HumanMessage("hi")]})
    assert "re-indexed" in ei.value.message


# --- _ainvoke_with_checkpoint_recovery --------------------------------------------------


@pytest.mark.asyncio
async def test_checkpoint_recovery_reraises_service_retired_untouched():
    from services.agent_execution_service import AgentExecutionService

    err = ServiceRetiredError(_svc(PAST), "ai")
    chain = MagicMock()
    chain.ainvoke = AsyncMock(side_effect=err)
    svc = AgentExecutionService.__new__(AgentExecutionService)
    agent = SimpleNamespace(agent_id=1, has_memory=True)
    with patch("services.agent_cache_service.is_missing_tool_output_error", return_value=True):
        with pytest.raises(ServiceRetiredError) as ei:
            await svc._ainvoke_with_checkpoint_recovery(chain, HumanMessage("x"), {"configurable": {}}, agent, "sid")
    assert ei.value is err
    assert chain.ainvoke.await_count == 1


@pytest.mark.asyncio
async def test_execute_chat_does_not_relog_service_retired(caplog):
    from services import agent_execution_service as aes

    svc = aes.AgentExecutionService.__new__(aes.AgentExecutionService)
    svc._prepare_turn = AsyncMock(side_effect=ServiceRetiredError(_svc(PAST), "ai"))
    aes.logger.addHandler(caplog.handler)
    try:
        with pytest.raises(ServiceRetiredError):
            await svc.execute_agent_chat_with_file_refs(1, "hi", user_context={"app_id": 3}, db=MagicMock())
    finally:
        aes.logger.removeHandler(caplog.handler)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# --- deferral of any retirement while building the tool agent ---------------------------


@pytest.mark.asyncio
async def test_iact_tool_defers_retired_middleware_model_and_records_metrics():
    agent = _tool_agent(None)  # the agent's own LLM is active
    retired = ServiceRetiredError(_svc(PAST), "ai")
    with patch.object(agentTools, "get_llm", return_value=object()), \
         patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)), \
         patch("tools.middleware.factory.build_agent_middlewares", side_effect=retired), \
         patch.object(agentTools.IACTTool, "_record_metrics") as record:
        tool_ = await agentTools.IACTTool.create(agent)
        with pytest.raises(ServiceRetiredError) as ei:
            await tool_._arun("hi")
    assert ei.value is retired
    record.assert_called_once()  # deferred failure is in the tool metrics


@pytest.mark.asyncio
async def test_iact_ocr_tool_non_retired_llm_errors_stay_lenient():
    agent = _tool_agent(None)
    with patch.object(agentTools, "get_llm", side_effect=RuntimeError("bad provider")), \
         patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)), \
         patch.object(agentTools, "create_langchain_agent", return_value=MagicMock()):
        tool_ = await agentTools.IACTOCRTool.create(agent)
    assert tool_.llm is None and tool_.deferred_error is None


# --- OCR: retired vision service surfaces instead of becoming a tool result -------------


def _ocr_service(**patches):
    from services import agent_execution_service as aes

    svc = aes.AgentExecutionService.__new__(aes.AgentExecutionService)
    ocr_agent = SimpleNamespace(
        agent_id=1, output_parser_id=None, text_system_prompt="t", vision_system_prompt="v", service_id=1, name="ocr",
    )
    svc.agent_execution_repo = MagicMock()
    svc.agent_execution_repo.get_ocr_agent_with_relationships.return_value = ocr_agent
    return aes, svc, ocr_agent


def test_process_pdf_vision_loop_reraises_service_retired():
    aes, svc, agent = _ocr_service()
    retired = ServiceRetiredError(_svc(PAST), "ai")

    def _get_llm(_agent, is_vision=False):
        if is_vision:
            raise retired
        return object()

    with patch.object(aes, "check_pdf_has_text", return_value=False), \
         patch.object(aes, "convert_pdf_to_images", return_value=["/tmp/p1.png"]), \
         patch.object(aes, "convert_image_to_base64", return_value="b64"), \
         patch.object(aes, "get_llm", side_effect=_get_llm):
        with pytest.raises(ServiceRetiredError):
            svc._process_pdf_with_ocr_sync(agent, "/tmp/x.pdf", MagicMock())


def test_process_pdf_text_model_reraises_service_retired():
    aes, svc, agent = _ocr_service()
    retired = ServiceRetiredError(_svc(PAST), "ai")

    def _get_llm(_agent, is_vision=False):
        if is_vision:
            return object()
        raise retired

    with patch.object(aes, "check_pdf_has_text", return_value=False), \
         patch.object(aes, "convert_pdf_to_images", return_value=["/tmp/p1.png"]), \
         patch.object(aes, "convert_image_to_base64", return_value="b64"), \
         patch.object(aes, "extract_text_from_image", return_value="text"), \
         patch.object(aes, "get_llm", side_effect=_get_llm):
        with pytest.raises(ServiceRetiredError):
            svc._process_pdf_with_ocr_sync(agent, "/tmp/x.pdf", MagicMock())


def test_process_pdf_outer_catch_reraises_without_error_log(caplog):
    aes, svc, agent = _ocr_service()
    aes.logger.addHandler(caplog.handler)
    try:
        with patch.object(aes, "check_pdf_has_text", side_effect=ServiceRetiredError(_svc(PAST), "ai")):
            with pytest.raises(ServiceRetiredError):
                svc._process_pdf_with_ocr_sync(agent, "/tmp/x.pdf", MagicMock())
    finally:
        aes.logger.removeHandler(caplog.handler)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


@pytest.mark.asyncio
async def test_execute_agent_ocr_reraises_service_retired_and_keeps_http_errors():
    from fastapi import HTTPException
    from models.ocr_agent import OCRAgent

    aes, svc, _ = _ocr_service()
    svc.agent_service = MagicMock()
    svc.agent_service.get_agent.return_value = MagicMock(spec=OCRAgent)
    svc._save_uploaded_file = AsyncMock(return_value="/tmp/does-not-exist.pdf")
    svc._process_pdf_with_ocr = AsyncMock(side_effect=ServiceRetiredError(_svc(PAST), "ai"))
    pdf = SimpleNamespace(filename="a.pdf")
    with pytest.raises(ServiceRetiredError):
        await svc.execute_agent_ocr(1, pdf, db=MagicMock())
    with pytest.raises(HTTPException) as ei:
        await svc.execute_agent_ocr(1, SimpleNamespace(filename="a.txt"), db=MagicMock())
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_ocr_tool_propagates_retired_vision_through_agent_chain(tmp_path):
    """Active text service + retired vision service: parent ainvoke raises, no ToolMessage carries the notice."""
    from services import agent_execution_service as aes

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    agent = _tool_agent(None)
    agent.name = "ocr_sub"
    retired = ServiceRetiredError(_svc(PAST), "ai")
    parent_model = _ToolCallingModel()

    with patch.object(agentTools, "get_llm", return_value=_ToolCallingModel()), \
         patch.object(agentTools.MCPClientManager, "get_client", new=AsyncMock(return_value=None)), \
         patch("db.database.SessionLocal", MagicMock()), \
         patch.object(aes.AgentExecutionService, "execute_agent_ocr", new=AsyncMock(side_effect=retired)):
        ocr_tool = await agentTools.IACTOCRTool.create(
            agent, attached_files=[{"type": "pdf", "file_path": str(pdf), "filename": "doc.pdf"}]
        )
        with pytest.raises(ServiceRetiredError):
            await ocr_tool._arun("extract")

        class _Calls(_ToolCallingModel):
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                msg = AIMessage(content="", tool_calls=[{"name": ocr_tool.name, "args": {"query": "x"}, "id": "c1"}])
                return ChatResult(generations=[ChatGeneration(message=msg)])

        chain = create_langchain_agent(model=_Calls(), tools=[ocr_tool])
        with pytest.raises(ServiceRetiredError):
            await chain.ainvoke({"messages": [HumanMessage("go")]})


def test_agent_turn_context_kwargs_and_nested_context_restored():
    from models.hitl_approval import ApprovalChannel
    from utils.service_lifecycle import agent_turn_context_kwargs, get_service_call_context, service_call_context

    assert agent_turn_context_kwargs(ApprovalChannel.MCP, {"app_id": 2, "scheduled_task_id": 9}, 5) == {
        "channel": "mcp", "app_id": 2, "resource_type": "scheduled_task", "resource_id": 9,
    }
    assert agent_turn_context_kwargs("a2a", None, 5)["resource_type"] == "agent"
    with service_call_context(channel="outer", resource_type="agent", resource_id=1):
        with service_call_context(**agent_turn_context_kwargs("inner", {}, 2)):
            pass
        assert get_service_call_context()["channel"] == "outer"


@pytest.mark.asyncio
async def test_execute_chat_resets_call_context_after_run():
    from services import agent_execution_service as aes
    from utils.service_lifecycle import get_service_call_context

    svc = aes.AgentExecutionService.__new__(aes.AgentExecutionService)
    seen = {}

    async def _prepare(**kw):
        seen.update(get_service_call_context())
        raise ServiceRetiredError(_svc(PAST), "ai")

    svc._prepare_turn = _prepare
    before = get_service_call_context()
    with pytest.raises(ServiceRetiredError):
        await svc.execute_agent_chat_with_file_refs(4, "hi", user_context={"app_id": 3}, db=MagicMock())
    assert seen["resource_id"] == 4 and seen["channel"] == "internal_sync"
    assert get_service_call_context() == before
