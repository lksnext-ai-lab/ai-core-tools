"""Integration tests: every consumer of a retired service surfaces the same message (step_012).

AC-7 (OCR vision, middleware model, transcription, video), AC-9 (MCP, A2A, scheduled task)
and AC-10 (background indexing marks the item failed, service ``last_error`` stays NULL).
Real test DB; provider SDKs are patched and asserted NOT called.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.integration._eos_enforcement_helpers import (  # noqa: F401  (fixtures)
    LLM_ANSWER,
    FakeToolChatModel,
    SessionProxy,
    ai_service,
    embedding_builders,
    embedding_service,
    fake_vector_store,
    future,
    guard_warnings,
    lifecycle_caplog,
    llm_builders,
    make_agent,
    make_repository,
    make_silo,
    past,
)
from tests.integration.routers.internal._eos_helpers import (
    attach_middleware,
    make_summarization_middleware,
    make_task,
)
from utils.service_lifecycle import ServiceRetiredError

pytestmark = pytest.mark.integration


def _message(svc, suffix=""):
    return f"Service {svc.name} was retired on {svc.end_of_service_at:%Y-%m-%d}.{suffix}"


# ---------------------------------------------------------------------------
# AC-7
# ---------------------------------------------------------------------------


class TestRetiredServiceInEveryConsumer:
    """AC-7: same error for OCR vision, middleware model, transcription and video services."""

    def test_ocr_agent_with_retired_vision_service(self, db, fake_app, fake_ai_service, llm_builders):
        from models.ocr_agent import OCRAgent
        from tools.aiServiceTools import get_llm

        vision = ai_service(db, fake_app, name="vision-retired", eos=past(2), notice="Use vision-2.")
        agent = make_agent(db, fake_app, fake_ai_service, cls=OCRAgent, vision_service_id=vision.service_id,
                           vision_system_prompt="v", text_system_prompt="t")
        db.refresh(agent)

        with pytest.raises(ServiceRetiredError) as info:
            get_llm(agent, is_vision=True)

        assert info.value.status_code == 409
        assert info.value.message == _message(vision, " Use vision-2.")
        assert not llm_builders.called
        # the (active) text model of the same OCR agent is untouched
        assert get_llm(agent, is_vision=False) is not None
        assert llm_builders.openai.call_count == 1

    def test_summarization_middleware_with_retired_model(self, db, fake_app, fake_ai_service, llm_builders):
        from tools.middleware.factory import build_agent_middlewares

        retired = ai_service(db, fake_app, name="summarizer-retired", eos=past(1))
        agent = make_agent(db, fake_app, fake_ai_service)
        attach_middleware(db, agent, make_summarization_middleware(db, fake_app, retired))
        db.refresh(agent)
        db.refresh(fake_app)

        with pytest.raises(ServiceRetiredError) as info:
            build_agent_middlewares(agent, FakeToolChatModel(responses=["x"]))

        assert info.value.message == _message(retired)
        assert not llm_builders.called

    def test_chat_fails_when_only_the_middleware_model_is_retired(
        self, client, db, fake_app, fake_ai_service, owner_headers, llm_builders
    ):
        retired = ai_service(db, fake_app, name="summarizer-retired-chat", eos=past(1))
        agent = make_agent(db, fake_app, fake_ai_service)  # the agent's own LLM is active
        attach_middleware(db, agent, make_summarization_middleware(db, fake_app, retired))
        db.refresh(agent)
        db.refresh(fake_app)

        resp = client.post(f"/internal/apps/{fake_app.app_id}/agents/{agent.agent_id}/chat",
                           data={"message": "hi"}, headers=owner_headers)

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == _message(retired)
        assert resp.json()["error_code"] == "SERVICE_RETIRED"

    def test_transcription_service_retired(self, db, fake_app):
        from tools.transcriptionTools import get_transcription_from_service

        retired = ai_service(db, fake_app, name="whisper-retired", eos=past(1))

        with patch("tools.transcriptionTools.transcribe_with_openai_whisper") as whisper:
            with pytest.raises(ServiceRetiredError) as info:
                get_transcription_from_service(retired, "/nonexistent/audio.wav")

        assert info.value.message == _message(retired)
        whisper.assert_not_called()

    def test_video_service_retired(self, db, fake_app, lifecycle_caplog):
        from services.video_analysis_service import VideoAnalysisService

        retired = ai_service(db, fake_app, name="video-retired", eos=past(1), supports_video=True)

        with patch("services.video_analysis_service._analyze_with_gemini") as gemini, \
                patch("services.video_analysis_service._analyze_with_vertex_ai") as vertex:
            with pytest.raises(ServiceRetiredError) as info:
                VideoAnalysisService.analyze_video("/nonexistent/video.mp4", retired.service_id, db)

        assert info.value.message == _message(retired)
        gemini.assert_not_called()
        vertex.assert_not_called()
        assert len(guard_warnings(lifecycle_caplog)) == 1

    @pytest.mark.parametrize("role", ["transcription", "video"])
    def test_media_task_records_message_on_the_media(self, db, fake_app, role, embedding_builders):
        """The silo media pipeline fails fast, before any download/transcription work."""
        from models.media import Media
        from tasks.media_tasks import process_media_task_sync

        emb = embedding_service(db, fake_app)
        retired = ai_service(db, fake_app, name=f"{role}-retired", eos=past(1), supports_video=True)
        active = ai_service(db, fake_app, name="whisper-active")
        silo = make_silo(
            db, fake_app, embedding_service_id=emb.service_id,
            transcription_service_id=(retired if role == "transcription" else active).service_id,
            video_ai_service_id=retired.service_id if role == "video" else None,
        )
        media = Media(silo_id=silo.silo_id, name="clip.mp4", source_type="upload", status="pending")
        db.add(media)
        db.flush()

        with patch("tasks.media_tasks.SessionLocal", return_value=SessionProxy(db)), \
                patch("tasks.media_tasks._extract_audio") as extract, \
                patch("tasks.media_tasks._download_youtube") as download, \
                patch("tools.transcriptionTools.transcribe_with_openai_whisper") as whisper:
            process_media_task_sync(media.media_id)

        db.refresh(media)
        assert media.status == "error"
        assert media.error_message == _message(retired)
        extract.assert_not_called()
        download.assert_not_called()
        whisper.assert_not_called()


# ---------------------------------------------------------------------------
# AC-9
# ---------------------------------------------------------------------------


def _mcp_server_exposing(db, app, agent):
    from models.mcp_server import MCPServer, MCPServerAgent

    server = MCPServer(name="eos-mcp", slug="eos-mcp", app_id=app.app_id)
    db.add(server)
    db.flush()
    db.add(MCPServerAgent(server_id=server.server_id, agent_id=agent.agent_id, tool_name_override="eos_tool"))
    db.flush()
    db.refresh(server)
    return server


class TestMcpChannel:
    @pytest.mark.asyncio
    async def test_tools_call_returns_is_error_result_with_message(
        self, db, fake_app, llm_builders, lifecycle_caplog
    ):
        from mcp_handler import server_handler as module

        retired = ai_service(db, fake_app, name="mcp-llm-retired", eos=past(1), notice="Use mcp-llm-2.")
        agent = make_agent(db, fake_app, retired, is_tool=True)
        server = _mcp_server_exposing(db, fake_app, agent)
        handler = module.MCPServerHandler(server.server_id, server.name, fake_app.app_id)

        with patch.object(module, "SessionLocal", return_value=SessionProxy(db)):
            response = await handler.handle_request({
                "jsonrpc": "2.0", "id": 7, "method": "tools/call",
                "params": {"name": "eos_tool", "arguments": {"message": "hi"}},
            })

        assert "error" not in response, response
        result = response["result"]
        assert result["isError"] is True
        assert result["content"] == [{"type": "text", "text": _message(retired, " Use mcp-llm-2.")}]
        assert not llm_builders.called
        warnings = guard_warnings(lifecycle_caplog)
        assert len(warnings) == 1
        assert "channel=mcp" in warnings[0].getMessage()


class TestA2AChannel:
    @pytest.mark.asyncio
    async def test_error_event_extra_is_sanitized_to_the_message(
        self, db, fake_app, fake_user, llm_builders, lifecycle_caplog
    ):
        from models.hitl_approval import ApprovalChannel
        from services.a2a_server.output_mapper import sanitize_error
        from services.agent_streaming_service import AgentStreamingService

        retired = ai_service(db, fake_app, name="a2a-llm-retired", eos=past(1), notice="Use a2a-llm-2.")
        agent = make_agent(db, fake_app, retired)
        user_context = {"app_id": fake_app.app_id, "api_key_id": None, "oauth": False,
                        "caller_type_override": "A2A"}

        events = [
            ev async for ev in AgentStreamingService(db).stream_agent_events(
                agent_id=agent.agent_id, message="hi", file_references=[], user_context=user_context,
                db=db, channel=ApprovalChannel.A2A,
            )
        ]

        errors = [ev for ev in events if ev.type == "error"]
        assert len(errors) == 1, [ev.type for ev in events]
        expected = _message(retired, " Use a2a-llm-2.")
        assert errors[0].data["message"] == expected
        assert errors[0].extra["error_kind"] == "service_retired"
        assert sanitize_error(errors[0].extra) == expected
        assert not llm_builders.called
        warnings = guard_warnings(lifecycle_caplog)
        assert len(warnings) == 1
        assert "channel=a2a" in warnings[0].getMessage()


class TestScheduledTaskChannel:
    @pytest.mark.asyncio
    async def test_run_is_recorded_failed_with_message_and_agent_invoked_once(
        self, db, fake_app, fake_user, llm_builders, lifecycle_caplog
    ):
        from models.scheduled_task import ScheduledTaskRun
        from scheduling import periodic_agent_task as module

        retired = ai_service(db, fake_app, name="sched-llm-retired", eos=past(1), notice="Use sched-llm-2.")
        agent = make_agent(db, fake_app, retired)
        task = make_task(db, fake_app, agent, fake_user.user_id)
        invoke = AsyncMock(side_effect=module._invoke_agent)  # the real agent execution, counted

        with patch.object(module, "SessionLocal", return_value=SessionProxy(db)), \
                patch.object(module, "invoke_agent_step", new=invoke):
            result = await module._run_scheduled_task(datetime.now(timezone.utc), task.id)

        expected = _message(retired, " Use sched-llm-2.")
        assert invoke.await_count == 1  # no retries of a run that cannot succeed
        assert result["error_code"] == "SERVICE_RETIRED"
        runs = db.query(ScheduledTaskRun).filter(ScheduledTaskRun.scheduled_task_id == task.id).all()
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert runs[0].error_summary == expected
        assert runs[0].output_text is None
        assert not llm_builders.called
        warnings = guard_warnings(lifecycle_caplog)
        assert len(warnings) == 1
        assert "channel=scheduled" in warnings[0].getMessage()
        assert f"resource_id={task.id}" in warnings[0].getMessage()


# ---------------------------------------------------------------------------
# AC-10
# ---------------------------------------------------------------------------


class TestBackgroundIndexing:
    def test_index_resource_marks_error_and_leaves_service_health_untouched(
        self, db, fake_app, embedding_builders, fake_vector_store, lifecycle_caplog
    ):
        from models.resource import Resource
        from services.silo_service import ResourceIndexingError, SiloService

        retired = embedding_service(db, fake_app, name="emb-retired", eos=past(1), notice="Use emb-2.")
        silo = make_silo(db, fake_app, embedding_service_id=retired.service_id)
        repo = make_repository(db, fake_app, silo)
        resource = Resource(name="doc.txt", uri="doc.txt", type="file", repository_id=repo.repository_id)
        db.add(resource)
        db.flush()

        with patch("services.silo_service.SessionLocal", return_value=SessionProxy(db)):
            with pytest.raises(ResourceIndexingError) as info:
                SiloService.index_resource(resource)
        assert isinstance(info.value.__cause__, ServiceRetiredError)

        expected = (f"{_message(retired)} Silos using it must be re-indexed with another embedding service."
                    " Use emb-2.")
        assert str(info.value) == expected
        db.refresh(resource)
        db.refresh(retired)
        assert resource.status == "error"
        assert resource.error_message == expected
        assert retired.last_error is None and retired.last_error_at is None
        assert not embedding_builders.called
        fake_vector_store.index_documents.assert_not_called()
        warnings = guard_warnings(lifecycle_caplog)
        assert len(warnings) == 1
        assert "kind=embedding" in warnings[0].getMessage()
        assert "channel=repository_indexing" in warnings[0].getMessage()
