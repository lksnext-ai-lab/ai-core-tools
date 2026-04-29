import base64
from unittest.mock import MagicMock

import httpx
import pytest
from a2a.server.agent_execution import RequestContext
from a2a.server.context import ServerCallContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    DataPart,
    FilePart,
    FileWithBytes,
    FileWithUri,
    Message,
    MessageSendParams,
    Part,
    Role,
    TextPart,
)

from services.a2a_agent_executor import MattinA2AAgentExecutor


class TestMattinA2AAgentExecutor:
    @pytest.mark.asyncio
    async def test_extract_message_inputs_serializes_data_parts(self):
        executor = MattinA2AAgentExecutor()

        context = RequestContext(
            request=MessageSendParams(
                message=Message(
                    message_id="msg-data",
                    role=Role.user,
                    parts=[
                        Part(root=TextPart(text="Process this payload")),
                        Part(root=DataPart(data={"key": "value", "count": 2})),
                    ],
                )
            )
        )

        message_text, upload_files = await executor._extract_message_inputs(context)

        assert message_text == 'Process this payload\n[Structured data]\n{"count": 2, "key": "value"}'
        assert upload_files == []

    @pytest.mark.asyncio
    async def test_execute_emits_input_required_task_with_text_and_file_artifacts(self, monkeypatch):
        executor = MattinA2AAgentExecutor()

        fake_session = MagicMock()
        monkeypatch.setattr("services.a2a_agent_executor.SessionLocal", lambda: fake_session)

        fake_agent = MagicMock()
        fake_agent.agent_id = 12
        fake_agent.app_id = 5
        fake_agent.a2a_enabled = True
        monkeypatch.setattr(
            "services.a2a_agent_executor.AgentService.get_agent",
            lambda self, db, agent_id: fake_agent,
        )

        captured = {}

        async def fake_resolve_chat_files(self, files, file_reference_ids, agent_id, user_context, conversation_id):
            captured["resolved_files"] = files
            return ["resolved-file-ref"]

        async def fake_stream_agent_chat(
            self,
            agent_id,
            message,
            file_references,
            search_params,
            user_context,
            conversation_id,
            db,
        ):
            captured["message"] = message
            captured["file_references"] = file_references
            yield (
                'data: {"type":"metadata","data":{"conversation_id":321,'
                '"agent_id":12,"agent_name":"A2A","has_memory":true}}\n\n'
            )
            yield 'data: {"type":"token","data":{"content":"Hello"}}\n\n'
            yield (
                'data: {"type":"done","data":{"response":"Hello",'
                '"conversation_id":321,'
                '"files":[{"file_id":"out-1","filename":"report.txt","file_type":"text"}]}}\n\n'
            )

        async def fake_list_attached_files(self, agent_id, user_context=None, conversation_id=None):
            return [
                {
                    "file_id": "out-1",
                    "filename": "report.txt",
                    "file_type": "text",
                    "file_path": "persistent/report.txt",
                    "mime_type": "text/plain",
                }
            ]

        monkeypatch.setattr(
            "services.a2a_agent_executor.FileManagementService.resolve_chat_files",
            fake_resolve_chat_files,
        )
        monkeypatch.setattr(
            "services.a2a_agent_executor.AgentStreamingService.stream_agent_chat",
            fake_stream_agent_chat,
        )
        monkeypatch.setattr(
            "services.a2a_agent_executor.FileManagementService.list_attached_files",
            fake_list_attached_files,
        )

        params = MessageSendParams(
            message=Message(
                message_id="msg-1",
                role=Role.user,
                parts=[
                    Part(root=TextPart(text="Summarize this")),
                    Part(
                        root=FilePart(
                            file=FileWithBytes(
                                name="note.txt",
                                mime_type="text/plain",
                                bytes=base64.b64encode(b"hello").decode(),
                            )
                        )
                    ),
                ],
            )
        )
        context = RequestContext(
            request=params,
            call_context=ServerCallContext(
                state={
                    "a2a": {
                        "app_id": 5,
                        "agent_id": 12,
                        "api_key": "test-key",
                        "api_key_id": 9,
                        "user_context": {"user_id": "apikey_123", "app_id": 5, "api_key": "test-key"},
                        "base_url": "http://testserver",
                    }
                }
            ),
        )
        queue = EventQueue()

        await executor.execute(context, queue)

        events = []
        while not queue.queue.empty():
            events.append(queue.queue.get_nowait())

        assert captured["message"] == "Summarize this"
        assert captured["file_references"] == ["resolved-file-ref"]
        assert any(getattr(event, "kind", None) == "artifact-update" for event in events)
        final_status = [event for event in events if getattr(event, "kind", None) == "status-update"][-1]
        assert final_status.status.state.value == "input-required"
        assert final_status.metadata["conversation_id"] == 321

    @pytest.mark.asyncio
    async def test_file_part_to_upload_retries_https_without_cert_verification(self, monkeypatch):
        executor = MattinA2AAgentExecutor()

        calls = []

        class FakeResponse:
            content = b"file-bytes"

            def raise_for_status(self):
                return None

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                calls.append(kwargs)
                self.verify = kwargs.get("verify", True)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, uri):
                if self.verify is False:
                    return FakeResponse()
                raise httpx.ConnectError("ssl failed")

        monkeypatch.setattr("services.a2a_agent_executor.httpx.AsyncClient", FakeAsyncClient)

        upload = await executor._file_part_to_upload(
            FilePart(
                file=FileWithUri(
                    uri="https://example.com/test.txt",
                    name="test.txt",
                    mime_type="text/plain",
                )
            )
        )

        assert upload.filename == "test.txt"
        assert len(calls) == 2
        assert calls[0] == {"timeout": 30.0}
        assert calls[1] == {"timeout": 30.0, "verify": False}

    @pytest.mark.asyncio
    async def test_file_part_to_upload_uses_placeholder_when_remote_uri_unreachable(self, monkeypatch):
        executor = MattinA2AAgentExecutor()

        class FailingResponse:
            def raise_for_status(self):
                request = httpx.Request("GET", "https://example.com/test.txt")
                response = httpx.Response(404, request=request)
                raise httpx.HTTPStatusError("not found", request=request, response=response)

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                self.verify = kwargs.get("verify", True)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, uri):
                return FailingResponse()

        monkeypatch.setattr("services.a2a_agent_executor.httpx.AsyncClient", FakeAsyncClient)

        upload = await executor._file_part_to_upload(
            FilePart(
                file=FileWithUri(
                    uri="https://example.com/test.txt",
                    name="test.txt",
                    mime_type="text/plain",
                )
            )
        )

        content = await upload.read()
        assert upload.filename == "test.txt"
        assert b"https://example.com/test.txt" in content
