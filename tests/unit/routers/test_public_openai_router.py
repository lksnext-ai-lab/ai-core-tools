"""
Tests for public API openai router.
"""
import base64
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from routers.public.v1 import openai as openai_module
from routers.public.v1.schemas_openai import OpenAIChatCompletionRequest, OpenAIMessage
from models.app import App


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_auth(mocker):
    mocker.patch.object(openai_module, "validate_api_key_for_app", return_value=None)


def _mock_app(mocker):
    # Mock get_app_by_identifier
    app = App(app_id=1, name="Test App", slug="test-app", enable_openai_api=True)
    mocker.patch.object(openai_module, "get_app_by_identifier", return_value=app)
    return app


def _mock_agent_service(mocker, has_memory=False, agent_id=1, output_parser_id=None):
    mock_cls = mocker.patch.object(openai_module, "AgentService")
    svc = mock_cls.return_value
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.app_id = 1
    agent.has_memory = has_memory
    agent.output_parser_id = output_parser_id
    agent.create_date = MagicMock()
    agent.create_date.timestamp.return_value = 1600000000
    svc.get_agent.return_value = agent
    svc.get_agents.return_value = [agent]
    return svc


def _mock_execution_service(mocker, result=None):
    mock_cls = mocker.patch.object(openai_module, "AgentExecutionService")
    svc = mock_cls.return_value
    if result is None:
        result = {
            "response": "Hello from OpenAI compatible API",
            "conversation_id": None,
            "metadata": {"usage": {"prompt_tokens": 10, "completion_tokens": 20}},
        }
    svc.execute_agent_chat_with_file_refs = AsyncMock(return_value=result)
    return svc

def _mock_file_management_service(mocker):
    mock_cls = mocker.patch.object(openai_module, "FileManagementService")
    svc = mock_cls.return_value
    file_ref_mock = MagicMock()
    file_ref_mock.file_id = "mocked-file-id"
    svc.upload_file = AsyncMock(return_value=file_ref_mock)
    return svc


class TestOpenAIRouter:
    @pytest.mark.asyncio
    async def test_chat_completions_string_content(self, mocker):
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)
        
        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[OpenAIMessage(role="user", content="Hello")],
            temperature=None,
            max_tokens=None,
        )
        
        result = await openai_module.chat_completions(
            app_id="1",
            request=req,
            api_key="key",
            db=MagicMock()
        )
        
        assert result.object == "chat.completion"
        assert result.choices[0].message.content == "Hello from OpenAI compatible API"
        exec_mock.execute_agent_chat_with_file_refs.assert_called_once()
        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert kwargs["message"] == "[Latest Input]\nuser: Hello"
        assert kwargs["file_references"] == []

    @pytest.mark.asyncio
    async def test_chat_completions_multipart_content_base64(self, mocker):
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)
        file_mock = _mock_file_management_service(mocker)
        
        # 1x1 png base64
        b64_img = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        
        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[
                OpenAIMessage(
                    role="user", 
                    content=[
                        {"type": "text", "text": "What is this?"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}}
                    ]
                )
            ],
            temperature=None,
            max_tokens=None,
        )
        
        result = await openai_module.chat_completions(
            app_id="1",
            request=req,
            api_key="key",
            db=MagicMock()
        )
        
        assert result.object == "chat.completion"
        
        file_mock.upload_file.assert_called_once()
        exec_mock.execute_agent_chat_with_file_refs.assert_called_once()
        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert kwargs["message"] == "[Latest Input]\nuser: What is this?"
        assert len(kwargs["file_references"]) == 1
        assert kwargs["file_references"][0].file_id == "mocked-file-id"

    @pytest.mark.asyncio
    async def test_chat_completions_multipart_content_url(self, mocker):
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)
        file_mock = _mock_file_management_service(mocker)

        # Bypass DNS / SSRF validation: make example.com resolve to a public IP
        mocker.patch(
            "routers.public.v1.openai.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        )

        # Mock httpx streaming: client.stream() is an async context manager that
        # yields a response whose aiter_bytes() produces chunks.
        fake_image_bytes = b"fake-image-bytes"

        async def _aiter_bytes(chunk_size=65536):
            yield fake_image_bytes

        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "image/jpeg"}
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_bytes = _aiter_bytes
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mocker.patch("routers.public.v1.openai.httpx.AsyncClient", return_value=mock_client)

        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[
                OpenAIMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "What is this?"},
                        {"type": "image_url", "image_url": {"url": "http://example.com/image.jpg"}}
                    ]
                )
            ],
            temperature=None,
            max_tokens=None,
        )

        result = await openai_module.chat_completions(
            app_id="1",
            request=req,
            api_key="key",
            db=MagicMock()
        )

        assert result.object == "chat.completion"

        mock_client.stream.assert_called_once_with("GET", "http://example.com/image.jpg", timeout=10.0)
        file_mock.upload_file.assert_called_once()

        exec_mock.execute_agent_chat_with_file_refs.assert_called_once()
        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert kwargs["message"] == "[Latest Input]\nuser: What is this?"
        assert len(kwargs["file_references"]) == 1

    @pytest.mark.asyncio
    async def test_chat_completions_with_history_and_system(self, mocker):
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)
        
        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[
                OpenAIMessage(role="system", content="You are an AI."),
                OpenAIMessage(role="user", content="Hi"),
                OpenAIMessage(role="assistant", content="Hello there!"),
                OpenAIMessage(role="user", content="How are you?")
            ],
            temperature=None,
            max_tokens=None,
        )
        
        result = await openai_module.chat_completions(
            app_id="1",
            request=req,
            api_key="key",
            db=MagicMock()
        )
        
        assert result.object == "chat.completion"
        exec_mock.execute_agent_chat_with_file_refs.assert_called_once()
        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        
        expected_message = (
            "--- Conversation History ---\n"
            "user: Hi\n\n"
            "assistant: Hello there!\n"
            "--- End of History ---\n\n"
            "[Latest Input]\n"
            "user: How are you?"
        )
        
        assert kwargs["message"] == expected_message


def _mock_streaming_service(mocker, events):
    """Return a mock AgentStreamingService whose stream_agent_chat yields *events*."""

    async def _gen(*args, **kwargs):
        for event in events:
            yield event

    mock_cls = mocker.patch.object(openai_module, "AgentStreamingService")
    svc = mock_cls.return_value
    svc.stream_agent_chat.return_value = _gen()
    return svc


async def _collect_sse(streaming_response) -> list[str]:
    """Drain a StreamingResponse and return each raw SSE line that starts with 'data: '."""
    chunks = []
    async for raw in streaming_response.body_iterator:
        if isinstance(raw, bytes):
            raw = raw.decode()
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data: "):
                chunks.append(line[6:])  # strip "data: " prefix
    return chunks


class TestListModels:
    @pytest.mark.asyncio
    async def test_only_memoryless_agents_returned(self, mocker):
        """Agents with has_memory=True must be excluded from /models."""
        _patch_auth(mocker)
        _mock_app(mocker)

        mock_cls = mocker.patch.object(openai_module, "AgentService")
        svc = mock_cls.return_value

        memoryless = MagicMock()
        memoryless.agent_id = 10
        memoryless.has_memory = False
        memoryless.create_date = MagicMock()
        memoryless.create_date.timestamp.return_value = 1700000000

        stateful = MagicMock()
        stateful.agent_id = 20
        stateful.has_memory = True
        stateful.create_date = MagicMock()
        stateful.create_date.timestamp.return_value = 1700000001

        svc.get_agents.return_value = [memoryless, stateful]

        result = await openai_module.list_models(
            app_id="1",
            api_key="key",
            db=MagicMock(),
        )

        model_ids = [m.id for m in result.data]
        assert "10" in model_ids
        assert "20" not in model_ids

    @pytest.mark.asyncio
    async def test_empty_when_all_agents_have_memory(self, mocker):
        _patch_auth(mocker)
        _mock_app(mocker)

        mock_cls = mocker.patch.object(openai_module, "AgentService")
        svc = mock_cls.return_value

        stateful = MagicMock()
        stateful.agent_id = 99
        stateful.has_memory = True
        svc.get_agents.return_value = [stateful]

        result = await openai_module.list_models(
            app_id="1",
            api_key="key",
            db=MagicMock(),
        )

        assert result.data == []


class TestStreamingChatCompletions:
    def _base_request(self, stream=True):
        return OpenAIChatCompletionRequest(
            model="1",
            messages=[OpenAIMessage(role="user", content="Hello")],
            stream=stream,
            temperature=None,
            max_tokens=None,
        )

    @pytest.mark.asyncio
    async def test_streaming_returns_streaming_response(self, mocker):
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        _mock_streaming_service(mocker, events=[])

        result = await openai_module.chat_completions(
            app_id="1",
            request=self._base_request(stream=True),
            api_key="key",
            db=MagicMock(),
        )

        assert isinstance(result, StreamingResponse)
        assert result.media_type == "text/event-stream"

    @pytest.mark.asyncio
    async def test_streaming_role_introduction_chunk(self, mocker):
        """First SSE chunk must carry delta.role == 'assistant'."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        _mock_streaming_service(mocker, events=[])

        result = await openai_module.chat_completions(
            app_id="1",
            request=self._base_request(stream=True),
            api_key="key",
            db=MagicMock(),
        )

        chunks = await _collect_sse(result)
        # The generator always yields a role-introduction chunk before iterating events
        assert len(chunks) >= 1
        intro = json.loads(chunks[0])
        assert intro["object"] == "chat.completion.chunk"
        assert intro["choices"][0]["delta"]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_streaming_token_events_become_content_chunks(self, mocker):
        """Each 'token' event must produce a chunk with delta.content."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)

        token_events = [
            'data: {"type": "token", "data": {"content": "Hello"}}',
            'data: {"type": "token", "data": {"content": " world"}}',
        ]
        _mock_streaming_service(mocker, events=token_events)

        result = await openai_module.chat_completions(
            app_id="1",
            request=self._base_request(stream=True),
            api_key="key",
            db=MagicMock(),
        )

        chunks = await _collect_sse(result)
        # chunks[0] = role intro, chunks[1..2] = tokens, last = [DONE]
        contents = [
            json.loads(c)["choices"][0]["delta"].get("content")
            for c in chunks[1:]
            if c != "[DONE]"
        ]
        assert "Hello" in contents
        assert " world" in contents

    @pytest.mark.asyncio
    async def test_streaming_done_event_sends_stop_and_done_sentinel(self, mocker):
        """A 'done' event must produce a finish_reason=stop chunk followed by [DONE]."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)

        done_event = 'data: {"type": "done", "data": ""}'
        _mock_streaming_service(mocker, events=[done_event])

        result = await openai_module.chat_completions(
            app_id="1",
            request=self._base_request(stream=True),
            api_key="key",
            db=MagicMock(),
        )

        chunks = await _collect_sse(result)
        assert chunks[-1] == "[DONE]"

        stop_chunk = json.loads(chunks[-2])
        assert stop_chunk["choices"][0]["finish_reason"] == "stop"
        assert stop_chunk["choices"][0]["delta"] == {}

    @pytest.mark.asyncio
    async def test_streaming_error_event_sends_error_content_and_stop(self, mocker):
        """An 'error' event must surface the error message with finish_reason=stop."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)

        error_event = 'data: {"type": "error", "data": {"message": "Something went wrong"}}'
        _mock_streaming_service(mocker, events=[error_event])

        result = await openai_module.chat_completions(
            app_id="1",
            request=self._base_request(stream=True),
            api_key="key",
            db=MagicMock(),
        )

        chunks = await _collect_sse(result)
        assert chunks[-1] == "[DONE]"

        # The error chunk is the second-to-last before [DONE]
        error_chunk = json.loads(chunks[-2])
        assert error_chunk["choices"][0]["finish_reason"] == "stop"
        assert "Something went wrong" in error_chunk["choices"][0]["delta"]["content"]

    @pytest.mark.asyncio
    async def test_streaming_all_chunks_share_same_completion_id(self, mocker):
        """All SSE chunks must carry the same completion id."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)

        events = [
            'data: {"type": "token", "data": {"content": "Hi"}}',
            'data: {"type": "done", "data": ""}',
        ]
        _mock_streaming_service(mocker, events=events)

        result = await openai_module.chat_completions(
            app_id="1",
            request=self._base_request(stream=True),
            api_key="key",
            db=MagicMock(),
        )

        chunks = await _collect_sse(result)
        parsed = [json.loads(c) for c in chunks if c != "[DONE]"]
        ids = {p["id"] for p in parsed}
        assert len(ids) == 1
        assert next(iter(ids)).startswith("chatcmpl-")

    @pytest.mark.asyncio
    async def test_streaming_rejects_agent_with_memory(self, mocker):
        """Streaming must be rejected when the agent has memory enabled."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker, has_memory=True)

        with pytest.raises(HTTPException) as exc_info:
            await openai_module.chat_completions(
                app_id="1",
                request=self._base_request(stream=True),
                api_key="key",
                db=MagicMock(),
            )

        assert exc_info.value.status_code == 400
        assert "memory" in exc_info.value.detail.lower()


class TestSSRFValidation:
    """Unit tests for _validate_image_url SSRF protection."""

    def test_non_http_scheme_rejected(self, mocker):
        with pytest.raises(HTTPException) as exc_info:
            openai_module._validate_image_url("file:///etc/passwd")
        assert exc_info.value.status_code == 400
        assert "scheme" in exc_info.value.detail.lower()

    def test_ftp_scheme_rejected(self, mocker):
        with pytest.raises(HTTPException) as exc_info:
            openai_module._validate_image_url("ftp://example.com/image.jpg")
        assert exc_info.value.status_code == 400

    def test_loopback_ipv4_rejected(self, mocker):
        mocker.patch(
            "routers.public.v1.openai.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("127.0.0.1", 0))],
        )
        with pytest.raises(HTTPException) as exc_info:
            openai_module._validate_image_url("http://localhost/image.jpg")
        assert exc_info.value.status_code == 400
        assert "private" in exc_info.value.detail.lower() or "reserved" in exc_info.value.detail.lower()

    def test_private_rfc1918_rejected(self, mocker):
        mocker.patch(
            "routers.public.v1.openai.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("192.168.1.100", 0))],
        )
        with pytest.raises(HTTPException) as exc_info:
            openai_module._validate_image_url("http://internal-service/image.jpg")
        assert exc_info.value.status_code == 400

    def test_link_local_rejected(self, mocker):
        # 169.254.169.254 is the AWS/GCP instance metadata endpoint
        mocker.patch(
            "routers.public.v1.openai.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("169.254.169.254", 0))],
        )
        with pytest.raises(HTTPException) as exc_info:
            openai_module._validate_image_url("http://169.254.169.254/latest/meta-data/")
        assert exc_info.value.status_code == 400

    def test_public_ip_accepted(self, mocker):
        mocker.patch(
            "routers.public.v1.openai.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        )
        # Should not raise
        openai_module._validate_image_url("https://example.com/image.jpg")

    def test_unresolvable_host_rejected(self, mocker):
        import socket as _socket
        mocker.patch(
            "routers.public.v1.openai.socket.getaddrinfo",
            side_effect=_socket.gaierror("Name or service not known"),
        )
        with pytest.raises(HTTPException) as exc_info:
            openai_module._validate_image_url("http://nonexistent.invalid/img.jpg")
        assert exc_info.value.status_code == 400


class TestResponseFormat:
    """Unit tests for FR-8: response_format support (AC-10)."""

    def _base_request(self, response_format=None):
        return OpenAIChatCompletionRequest(
            model="1",
            messages=[OpenAIMessage(role="user", content="Hello")],
            response_format=response_format,
        )

    @pytest.mark.asyncio
    async def test_json_object_injects_json_instruction(self, mocker):
        """response_format json_object must inject a JSON instruction into the message."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)

        req = self._base_request(response_format={"type": "json_object"})
        await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert "[System Instruction]" in kwargs["message"]
        assert "JSON" in kwargs["message"]

    @pytest.mark.asyncio
    async def test_json_schema_injects_schema_string(self, mocker):
        """response_format json_schema must inject the schema JSON into the message."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)

        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        req = self._base_request(response_format={"type": "json_schema", "json_schema": schema})
        await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert "[System Instruction]" in kwargs["message"]
        assert '"answer"' in kwargs["message"]

    @pytest.mark.asyncio
    async def test_text_format_no_injection(self, mocker):
        """response_format text must not inject any system instruction."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)

        req = self._base_request(response_format={"type": "text"})
        await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert "[System Instruction]" not in kwargs["message"]

    @pytest.mark.asyncio
    async def test_omitted_response_format_no_injection(self, mocker):
        """Omitting response_format must not inject any system instruction."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)

        req = self._base_request(response_format=None)
        await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert "[System Instruction]" not in kwargs["message"]

    @pytest.mark.asyncio
    async def test_unknown_format_type_no_injection(self, mocker):
        """Unknown response_format type must be silently ignored (no injection)."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)

        req = self._base_request(response_format={"type": "audio"})
        await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert "[System Instruction]" not in kwargs["message"]


class TestAgentOutputParserIntegration:
    """Tests for agent output_parser_id → response_format reflection (agent-enforced JSON)."""

    @pytest.mark.asyncio
    async def test_dict_response_serialized_as_json_string(self, mocker):
        """When agent has output_parser_id and response is a dict, content must be valid JSON."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker, output_parser_id=42)
        _mock_execution_service(
            mocker,
            result={
                "response": {"name": "Alice", "age": 30},
                "conversation_id": None,
                "metadata": {"usage": {"prompt_tokens": 5, "completion_tokens": 10}},
            },
        )

        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[OpenAIMessage(role="user", content="Give me JSON")],
        )
        result = await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        content = result.choices[0].message.content
        # Must be valid JSON (not Python repr like {'name': 'Alice'})
        parsed = json.loads(content)
        assert parsed == {"name": "Alice", "age": 30}
        assert result.response_format == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_response_format_set_for_string_json_response(self, mocker):
        """When agent has output_parser_id and response is already a JSON string, response_format is set."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker, output_parser_id=7)
        _mock_execution_service(
            mocker,
            result={
                "response": '{"status": "ok"}',
                "conversation_id": None,
                "metadata": {},
            },
        )

        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[OpenAIMessage(role="user", content="Check")],
        )
        result = await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        assert result.response_format == {"type": "json_object"}
        assert result.choices[0].message.content == '{"status": "ok"}'

    @pytest.mark.asyncio
    async def test_no_response_format_without_output_parser(self, mocker):
        """When agent has no output_parser_id, response_format is None in the response."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker, output_parser_id=None)
        _mock_execution_service(mocker)

        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[OpenAIMessage(role="user", content="Hello")],
        )
        result = await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        assert result.response_format is None


class TestNewContentPartTypes:
    """Tests for input_audio and file content part types."""

    @pytest.mark.asyncio
    async def test_input_audio_wav_is_uploaded(self, mocker):
        """input_audio part (WAV) should be decoded and uploaded as a file reference."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)
        file_mock = _mock_file_management_service(mocker)

        # Minimal valid WAV bytes (44-byte header filled with zeros is enough for the test)
        raw_audio = b"\x00" * 64
        audio_b64 = base64.b64encode(raw_audio).decode()

        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[
                OpenAIMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "Transcribe this"},
                        {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}},
                    ],
                )
            ],
            temperature=None,
            max_tokens=None,
        )

        result = await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        assert result.object == "chat.completion"
        file_mock.upload_file.assert_called_once()
        upload_call = file_mock.upload_file.call_args
        uploaded_filename = upload_call.kwargs["file"].filename
        assert uploaded_filename.startswith("audio_")
        assert uploaded_filename.endswith(".wav")

        exec_mock.execute_agent_chat_with_file_refs.assert_called_once()
        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert len(kwargs["file_references"]) == 1

    @pytest.mark.asyncio
    async def test_input_audio_mp3_is_uploaded(self, mocker):
        """input_audio part (MP3) should produce a filename ending in .mp3."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        _mock_execution_service(mocker)
        file_mock = _mock_file_management_service(mocker)

        raw_audio = b"\xff\xfb" + b"\x00" * 62  # minimal MP3-like bytes
        audio_b64 = base64.b64encode(raw_audio).decode()

        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[
                OpenAIMessage(
                    role="user",
                    content=[
                        {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "mp3"}},
                    ],
                )
            ],
            temperature=None,
            max_tokens=None,
        )

        await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        file_mock.upload_file.assert_called_once()
        uploaded_filename = file_mock.upload_file.call_args.kwargs["file"].filename
        assert uploaded_filename.endswith(".mp3")

    @pytest.mark.asyncio
    async def test_file_part_with_file_data_is_uploaded(self, mocker):
        """file part with base64 file_data should decode and upload correctly."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)
        file_mock = _mock_file_management_service(mocker)

        raw_bytes = b"Hello, this is a test document."
        file_b64 = base64.b64encode(raw_bytes).decode()

        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[
                OpenAIMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "Summarise this"},
                        {
                            "type": "file",
                            "file": {"file_data": file_b64, "filename": "report.txt"},
                        },
                    ],
                )
            ],
            temperature=None,
            max_tokens=None,
        )

        result = await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        assert result.object == "chat.completion"
        file_mock.upload_file.assert_called_once()
        uploaded_filename = file_mock.upload_file.call_args.kwargs["file"].filename
        assert uploaded_filename == "report.txt"

        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert len(kwargs["file_references"]) == 1

    @pytest.mark.asyncio
    async def test_file_part_with_file_id_uses_existing_reference(self, mocker):
        """file part with file_id should fetch the existing FileReference (no upload)."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)
        file_mock = _mock_file_management_service(mocker)

        existing_ref = MagicMock()
        existing_ref.file_id = "existing-file-123"
        file_mock.get_file_reference = AsyncMock(return_value=existing_ref)

        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[
                OpenAIMessage(
                    role="user",
                    content=[
                        {"type": "file", "file": {"file_id": "existing-file-123"}},
                    ],
                )
            ],
            temperature=None,
            max_tokens=None,
        )

        await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        file_mock.upload_file.assert_not_called()
        file_mock.get_file_reference.assert_called_once_with("existing-file-123")

        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert len(kwargs["file_references"]) == 1
        assert kwargs["file_references"][0].file_id == "existing-file-123"

    @pytest.mark.asyncio
    async def test_file_part_with_unknown_file_id_skips_reference(self, mocker):
        """file part with unknown file_id should log a warning and not add a reference."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)
        file_mock = _mock_file_management_service(mocker)

        file_mock.get_file_reference = AsyncMock(return_value=None)

        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[
                OpenAIMessage(
                    role="user",
                    content=[
                        {"type": "file", "file": {"file_id": "nonexistent-id"}},
                    ],
                )
            ],
            temperature=None,
            max_tokens=None,
        )

        await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        file_mock.upload_file.assert_not_called()
        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert len(kwargs["file_references"]) == 0

    @pytest.mark.asyncio
    async def test_mixed_content_parts_text_audio_file(self, mocker):
        """A message with text + input_audio + file parts should upload two files."""
        _patch_auth(mocker)
        _mock_app(mocker)
        _mock_agent_service(mocker)
        exec_mock = _mock_execution_service(mocker)
        file_mock = _mock_file_management_service(mocker)
        # Return unique mocks so we can count references
        file_mock.upload_file = AsyncMock(side_effect=[
            MagicMock(file_id="ref-audio"),
            MagicMock(file_id="ref-file"),
        ])

        audio_b64 = base64.b64encode(b"\x00" * 32).decode()
        file_b64 = base64.b64encode(b"data").decode()

        req = OpenAIChatCompletionRequest(
            model="1",
            messages=[
                OpenAIMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "Describe both"},
                        {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}},
                        {"type": "file", "file": {"file_data": file_b64, "filename": "data.csv"}},
                    ],
                )
            ],
            temperature=None,
            max_tokens=None,
        )

        result = await openai_module.chat_completions(
            app_id="1", request=req, api_key="key", db=MagicMock()
        )

        assert result.object == "chat.completion"
        assert file_mock.upload_file.call_count == 2
        kwargs = exec_mock.execute_agent_chat_with_file_refs.call_args.kwargs
        assert len(kwargs["file_references"]) == 2

