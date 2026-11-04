"""Regression: tools/list and tools/call load the MCP server through ``_get_mcp_server``."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_handler import server_handler as module


def test_get_mcp_server_loads_by_server_and_app():
    handler = module.MCPServerHandler(1, "srv", 2, api_key_id=3)
    session = MagicMock()
    with patch("repositories.mcp_server_repository.MCPServerRepository.get_by_id_and_app_id") as get:
        result = handler._get_mcp_server(session)
    get.assert_called_once_with(session, 1, 2)
    assert result is get.return_value


def test_tools_list_reaches_server_lookup():
    handler = module.MCPServerHandler(1, "srv", 2, api_key_id=3)
    session = MagicMock()
    with (
        patch.object(module, "SessionLocal", return_value=session),
        patch.object(handler, "_get_mcp_server", return_value=None) as lookup,
        pytest.raises(module.MCPError, match="MCP server not found"),
    ):
        handler._handle_tools_list({})
    lookup.assert_called_once_with(session)
