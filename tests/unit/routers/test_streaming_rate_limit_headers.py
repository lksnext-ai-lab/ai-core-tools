"""
Response-level regression tests for SSE streaming endpoints.

Each of the four streaming endpoints below computes rate-limit values via
`apply_agent_rate_limit(..., response.headers)`, writing them onto the
FastAPI-injected `Response` object. But each endpoint then builds and returns
a brand new `StreamingResponse` with its own header set — the rate-limit
values written to `response.headers` are never copied over, so a real HTTP
client never sees `X-RateLimit-Limit` / `X-RateLimit-Remaining` /
`X-RateLimit-Reset` on a streaming call, even though they are present on
non-streaming calls to the same endpoints.

These tests exercise the real returned `StreamingResponse` object (not a
mock) and assert the rate-limit headers are present on it, alongside the
pre-existing SSE headers (event-stream media type, Cache-Control,
Connection, X-Accel-Buffering).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Response
from fastapi.responses import StreamingResponse

from services.rate_limit_service import RateLimitService


def _assert_rate_limit_headers_present(result: StreamingResponse) -> None:
    headers = result.headers
    assert "x-ratelimit-limit" in headers
    assert "x-ratelimit-remaining" in headers
    assert "x-ratelimit-reset" in headers
    assert headers["x-ratelimit-limit"] == "10"
    assert headers["x-ratelimit-remaining"] == "9"


# ---------------------------------------------------------------------------
# Public chat streaming — backend/routers/public/v1/chat.py
# ---------------------------------------------------------------------------

class TestPublicChatStreamHeaders:
    @pytest.mark.asyncio
    async def test_streaming_response_carries_rate_limit_headers(
        self, mocker, monkeypatch
    ):
        import routers.public.v1.chat as chat_module
        import routers.controls.rate_limit as rate_limit_module

        monkeypatch.setattr(rate_limit_module, "rate_limit_service", RateLimitService())

        agent = MagicMock()
        agent.app = SimpleNamespace(app_id=1, agent_rate_limit=10)
        agent.has_memory = False

        mocker.patch.object(chat_module, "validate_api_key_for_app", return_value=None)
        mocker.patch.object(
            chat_module, "validate_agent_ownership", return_value=agent
        )
        mocker.patch(
            "services.file_management_service.FileManagementService.resolve_chat_files",
            new_callable=AsyncMock,
            return_value=[],
        )
        mock_streaming_cls = mocker.patch.object(chat_module, "AgentStreamingService")
        svc = mock_streaming_cls.return_value

        async def _gen():
            yield "data: token\n\n"

        svc.stream_agent_chat.return_value = _gen()

        response_obj = Response()
        result = await chat_module.call_agent_stream(
            app_id=1,
            agent_id=5,
            message="hi",
            api_key="key",
            db=MagicMock(),
            response=response_obj,
            files=[],
            file_references=None,
            search_params=None,
            conversation_id=None,
            user_token=None,
        )

        assert isinstance(result, StreamingResponse)
        assert result.media_type == "text/event-stream"
        _assert_rate_limit_headers_present(result)
        assert result.headers["cache-control"] == "no-cache"
        assert result.headers["connection"] == "keep-alive"
        assert result.headers["x-accel-buffering"] == "no"


# ---------------------------------------------------------------------------
# Public approval-resume streaming — backend/routers/public/v1/approvals.py
# ---------------------------------------------------------------------------

class TestApprovalResumeStreamHeaders:
    @pytest.mark.asyncio
    async def test_streaming_response_carries_rate_limit_headers(
        self, mocker, monkeypatch
    ):
        import routers.public.v1.approvals as approvals_module
        import routers.controls.rate_limit as rate_limit_module

        monkeypatch.setattr(rate_limit_module, "rate_limit_service", RateLimitService())

        resume = SimpleNamespace(
            approval=SimpleNamespace(agent_id=5, conversation_id=99)
        )
        agent = MagicMock()
        agent.app_id = 1
        agent.app = SimpleNamespace(app_id=1, agent_rate_limit=10)

        mocker.patch.object(
            approvals_module, "validate_api_key_for_app", return_value=None
        )
        mocker.patch.object(
            approvals_module, "create_api_key_user_context", return_value={}
        )
        mocker.patch.object(
            approvals_module.approvals.Requester,
            "from_user_context",
            staticmethod(lambda ctx: object()),
        )
        mocker.patch.object(approvals_module.approvals, "get_for_requester", return_value=resume.approval)
        mocker.patch.object(approvals_module.approvals, "prepare_decisions", return_value=None)
        mocker.patch.object(
            approvals_module.approvals, "prepare_resume", return_value=resume
        )
        mock_agent_service_cls = mocker.patch.object(approvals_module, "AgentService")
        mock_agent_service_cls.return_value.get_agent.return_value = agent

        mock_streaming_cls = mocker.patch.object(approvals_module, "AgentStreamingService")
        svc = mock_streaming_cls.return_value

        async def _gen():
            yield "data: token\n\n"

        svc.stream_agent_chat.return_value = _gen()

        response_obj = Response()
        result = await approvals_module.decide_approval_stream(
            app_id=1,
            approval_id="approval-id",
            body=SimpleNamespace(decisions=[]),
            api_key="key",
            db=MagicMock(),
            response=response_obj,
        )

        assert isinstance(result, StreamingResponse)
        assert result.media_type == "text/event-stream"
        _assert_rate_limit_headers_present(result)
        assert result.headers["cache-control"] == "no-cache"
        assert result.headers["connection"] == "keep-alive"
        assert result.headers["x-accel-buffering"] == "no"


# ---------------------------------------------------------------------------
# OpenAI-compatible streaming chat — backend/routers/public/v1/openai.py
# ---------------------------------------------------------------------------

class TestOpenAIStreamHeaders:
    @pytest.mark.asyncio
    async def test_streaming_response_carries_rate_limit_headers(
        self, mocker, monkeypatch
    ):
        import routers.public.v1.openai as openai_module
        import routers.controls.rate_limit as rate_limit_module
        from routers.public.v1.schemas_openai import (
            OpenAIChatCompletionRequest,
            OpenAIMessage,
        )
        from models.app import App

        monkeypatch.setattr(rate_limit_module, "rate_limit_service", RateLimitService())

        app = App(app_id=1, name="Test App", slug="test-app", enable_openai_api=True, agent_rate_limit=10)
        mocker.patch.object(openai_module, "get_app_by_identifier", return_value=app)
        mocker.patch.object(
            openai_module, "validate_api_key_for_app", return_value=None
        )

        agent = MagicMock()
        agent.agent_id = 1
        agent.app_id = 1
        agent.has_memory = False
        agent.output_parser_id = None
        mock_agent_service_cls = mocker.patch.object(openai_module, "AgentService")
        mock_agent_service_cls.return_value.get_agent.return_value = agent

        mock_streaming_cls = mocker.patch.object(openai_module, "AgentStreamingService")
        svc = mock_streaming_cls.return_value

        async def _gen(*args, **kwargs):
            if False:
                yield ""

        svc.stream_agent_chat.return_value = _gen()

        request = OpenAIChatCompletionRequest(
            model="1",
            messages=[OpenAIMessage(role="user", content="Hello")],
            stream=True,
            temperature=None,
            max_tokens=None,
        )

        response_obj = Response()
        result = await openai_module.chat_completions(
            app_id="1",
            request=request,
            api_key="key",
            db=MagicMock(),
            response=response_obj,
        )

        assert isinstance(result, StreamingResponse)
        assert result.media_type == "text/event-stream"
        _assert_rate_limit_headers_present(result)


# ---------------------------------------------------------------------------
# Marketplace streaming chat — backend/routers/internal/marketplace.py
# ---------------------------------------------------------------------------

class TestMarketplaceChatStreamHeaders:
    @pytest.mark.asyncio
    async def test_streaming_response_carries_rate_limit_headers(
        self, mocker, monkeypatch
    ):
        import routers.internal.marketplace as marketplace_module
        import routers.controls.rate_limit as rate_limit_module

        monkeypatch.setattr(rate_limit_module, "rate_limit_service", RateLimitService())

        conversation = SimpleNamespace(agent_id=11)
        agent = SimpleNamespace(
            agent_id=11,
            app_id=1,
            app=SimpleNamespace(app_id=1, agent_rate_limit=10),
            has_memory=False,
        )

        def fake_prepare(conversation_id, user_id, db, response_headers):
            from routers.controls.rate_limit import apply_agent_rate_limit

            apply_agent_rate_limit(agent.app, agent.agent_id, response_headers)
            return conversation, agent

        monkeypatch.setattr(
            marketplace_module, "_prepare_marketplace_chat", fake_prepare
        )
        monkeypatch.setattr(
            marketplace_module, "_extract_jwt_token", lambda request: None
        )
        mocker.patch(
            "services.file_management_service.FileManagementService.resolve_chat_files",
            new_callable=AsyncMock,
            return_value=[],
        )
        mock_streaming_cls = mocker.patch.object(
            marketplace_module, "AgentStreamingService"
        )
        svc = mock_streaming_cls.return_value

        async def _gen():
            yield "data: token\n\n"

        svc.stream_agent_chat.return_value = _gen()

        current_user = SimpleNamespace(
            identity=SimpleNamespace(id="42", email="user@example.com")
        )
        response_obj = Response()
        result = await marketplace_module.marketplace_chat_stream(
            conversation_id=1,
            request=MagicMock(),
            message="hi",
            db=MagicMock(),
            current_user=current_user,
            response=response_obj,
            files=[],
            file_references=None,
        )

        assert isinstance(result, StreamingResponse)
        assert result.media_type == "text/event-stream"
        _assert_rate_limit_headers_present(result)
        assert result.headers["cache-control"] == "no-cache"
        assert result.headers["connection"] == "keep-alive"
        assert result.headers["x-accel-buffering"] == "no"
