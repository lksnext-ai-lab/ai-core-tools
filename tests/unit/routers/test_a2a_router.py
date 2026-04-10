from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.responses import StreamingResponse

from routers import a2a as a2a_module


class TestA2ARouter:
    @pytest.mark.asyncio
    async def test_get_root_agent_card_delegates_to_configured_slug_agent(self, mocker):
        request = MagicMock(spec=Request)
        db = MagicMock()
        mock_get_by_slug = mocker.patch.object(
            a2a_module,
            "get_agent_card_by_slug",
            new=AsyncMock(return_value={"card": "ok"}),
        )
        mocker.patch.object(a2a_module, "ROOT_AGENT_CARD_APP_SLUG", "cluedo")
        mocker.patch.object(a2a_module, "ROOT_AGENT_CARD_AGENT_ID", 2)

        result = await a2a_module.get_root_agent_card(request=request, db=db)

        assert result == {"card": "ok"}
        mock_get_by_slug.assert_awaited_once_with("cluedo", 2, request, db)

    @pytest.mark.asyncio
    async def test_get_agent_card_by_id_builds_public_payload(self, mocker):
        app = MagicMock(app_id=7, slug="workspace")
        agent = MagicMock(agent_id=11)
        request = MagicMock(spec=Request)

        mocker.patch.object(
            a2a_module,
            "_resolve_enabled_agent_by_app_id",
            return_value=(app, agent),
        )

        mock_build_payload = mocker.patch.object(
            a2a_module,
            "_build_public_agent_card_payload",
            return_value={"card": "ok"},
        )

        result = await a2a_module.get_agent_card_by_id(
            app_id=7,
            agent_id=11,
            request=request,
            db=MagicMock(),
        )

        assert result == {"card": "ok"}
        mock_build_payload.assert_called_once_with(
            request,
            app,
            agent,
            app_id=7,
        )

    @pytest.mark.asyncio
    async def test_rpc_by_id_validates_target_and_delegates(self, mocker):
        app = MagicMock(app_id=7, slug="workspace")
        agent = MagicMock(agent_id=11)
        request = MagicMock(spec=Request)
        response = MagicMock()

        mocker.patch.object(
            a2a_module,
            "_resolve_enabled_agent_by_app_id",
            return_value=(app, agent),
        )
        mock_handle = mocker.patch.object(
            a2a_module,
            "_handle_rpc_request",
            new=AsyncMock(return_value={"jsonrpc": "2.0"}),
        )

        result = await a2a_module.rpc_by_id(
            app_id=7,
            agent_id=11,
            request=request,
            response=response,
            api_key="test-key",
            db=MagicMock(),
        )

        assert result == {"jsonrpc": "2.0"}
        mock_handle.assert_awaited_once()

    def test_build_authenticated_extended_card_payload_includes_extended_fields(self, mocker):
        request = MagicMock(spec=Request)
        request.base_url = "http://testserver/"
        app = SimpleNamespace(app_id=7, slug="workspace")
        agent = SimpleNamespace(
            agent_id=11,
            name="Test Agent",
            description="Helpful",
            a2a_name_override=None,
            a2a_description_override=None,
            a2a_skill_tags=None,
            a2a_examples=None,
        )

        payload = a2a_module._build_authenticated_extended_card_payload(
            request,
            app,
            agent,
            app_slug="workspace",
        )

        assert payload["agentId"] == 11
        assert payload["supportsAuthenticatedExtendedCard"] is True
        assert payload["capabilities"]["skills"][0]["inputOutputModes"] == [
            "text",
            "file",
            "data",
        ]
        assert "file" in payload["defaultInputModes"]
        assert "data" in payload["defaultInputModes"]
        assert payload["authentication"]["required"] is True
        assert payload["endpoints"]["rpc"].endswith("/a2a/v1/apps/workspace/agents/11")
        assert payload["endpoints"]["authenticatedExtendedCard"].endswith(
            "/a2a/v1/apps/workspace/agents/agent/authenticatedExtendedCard"
        )

    @pytest.mark.asyncio
    async def test_handle_rpc_request_returns_extended_card_for_both_method_aliases(self, mocker):
        request = MagicMock(spec=Request)
        request.json = AsyncMock(
            side_effect=[
                {"jsonrpc": "2.0", "id": 9, "method": "agent/authenticatedExtendedCard", "params": {}},
                {"jsonrpc": "2.0", "id": 10, "method": "agent/getAuthenticatedExtendedCard", "params": {}},
            ]
        )
        request.state = MagicMock()
        request.base_url = "http://testserver/"
        response = MagicMock()
        db = MagicMock()
        app = MagicMock(app_id=7, slug="workspace")
        agent = MagicMock(agent_id=11)

        mocker.patch.object(a2a_module, "validate_api_key_for_app", return_value=MagicMock(key_id=1))
        mocker.patch.object(a2a_module, "enforce_allowed_origins")
        mocker.patch.object(a2a_module, "enforce_app_rate_limit")
        mocker.patch.object(a2a_module, "_set_request_state")
        mocker.patch.object(
            a2a_module,
            "_build_authenticated_extended_card_payload",
            return_value={"agentId": 11, "name": "Test Agent"},
        )

        first = await a2a_module._handle_rpc_request(
            request,
            response,
            db,
            app,
            agent,
            "test-key",
            app_slug="workspace",
        )
        second = await a2a_module._handle_rpc_request(
            request,
            response,
            db,
            app,
            agent,
            "test-key",
            app_slug="workspace",
        )

        assert first.body == b'{"jsonrpc":"2.0","id":9,"result":{"agentId":11,"name":"Test Agent"}}'
        assert second.body == b'{"jsonrpc":"2.0","id":10,"result":{"agentId":11,"name":"Test Agent"}}'

    def test_normalize_stream_headers_adds_sse_cache_directives(self):
        async def event_stream():
            yield b"data: {}\n\n"

        response = StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store"},
        )

        normalized = a2a_module._normalize_stream_headers(response)

        assert normalized.headers["Cache-Control"] == "no-cache, no-store"
        assert normalized.headers["X-Accel-Buffering"] == "no"

    def test_normalize_stream_headers_leaves_non_stream_responses_unchanged(self):
        response = MagicMock()
        response.headers = {"content-type": "application/json"}

        normalized = a2a_module._normalize_stream_headers(response)

        assert normalized is response
        assert "Cache-Control" not in normalized.headers

    def test_normalize_transport_part_aliases_converts_file_ref_part(self):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": "msg-1",
                    "role": "user",
                    "parts": [
                        {"kind": "text", "text": "Analyze this file"},
                        {
                            "kind": "fileRef",
                            "fileRef": {
                                "uri": "https://example.com/test-file.txt",
                                "mimeType": "text/plain",
                                "name": "test-file.txt",
                            },
                            "metadata": {"source": "transport-test"},
                        },
                    ],
                }
            },
        }

        normalized = a2a_module._normalize_transport_part_aliases(payload)

        file_part = normalized["params"]["message"]["parts"][1]
        assert file_part == {
            "kind": "file",
            "file": {
                "uri": "https://example.com/test-file.txt",
                "mimeType": "text/plain",
                "name": "test-file.txt",
            },
            "metadata": {"source": "transport-test"},
        }

    def test_normalize_transport_part_aliases_converts_file_url_and_wraps_array_data(self):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": "msg-1",
                    "role": "user",
                    "parts": [
                        {
                            "kind": "file",
                            "file": {
                                "url": "https://example.com/test-file.txt",
                                "mimeType": "text/plain",
                                "name": "test-file.txt",
                                "sizeInBytes": 1024,
                            },
                        },
                        {
                            "kind": "data",
                            "data": [
                                {"name": "Alice"},
                                {"name": "Bob"},
                            ],
                        },
                    ],
                }
            },
        }

        normalized = a2a_module._normalize_transport_part_aliases(payload)

        assert normalized["params"]["message"]["parts"][0]["file"] == {
            "uri": "https://example.com/test-file.txt",
            "mimeType": "text/plain",
            "name": "test-file.txt",
            "sizeInBytes": 1024,
        }
        assert normalized["params"]["message"]["parts"][1]["data"] == {
            "value": [
                {"name": "Alice"},
                {"name": "Bob"},
            ]
        }
