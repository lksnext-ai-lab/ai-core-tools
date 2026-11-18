"""MCP tools/call maps ServiceRetiredError to an isError tool result (step_006)."""

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_handler import server_handler as module
from utils.service_lifecycle import ServiceRetiredError


def _retired_error() -> ServiceRetiredError:
    service = SimpleNamespace(
        service_id=5, name="old-llm", end_of_service_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        deprecation_notice="Use new-llm.",
    )
    return ServiceRetiredError(service, "ai")


@pytest.mark.asyncio
async def test_tools_call_returns_is_error_result_with_message(caplog):
    error = _retired_error()
    handler = module.MCPServerHandler(1, "srv", 2, api_key_id=3)
    handler.agent_execution_service = MagicMock()
    handler.agent_execution_service.execute_agent_chat_with_file_refs = AsyncMock(side_effect=error)
    agent = SimpleNamespace(agent_id=9, is_tool=True)
    session = MagicMock()
    with (
        patch.object(module, "SessionLocal", return_value=session),
        patch.object(handler, "_get_mcp_server", return_value=MagicMock()),
        patch.object(handler, "_find_agent_by_tool_name", return_value=agent),
        caplog.at_level(logging.WARNING),
    ):
        result = await handler._handle_tools_call({"name": "tool", "arguments": {"message": "hi"}})

    assert result == {"content": [{"type": "text", "text": error.message}], "isError": True}
    assert "Use new-llm." in result["content"][0]["text"]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    session.close.assert_called_once()
