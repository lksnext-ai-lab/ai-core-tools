import pytest
import asyncio

from services.mcp_config_service import MCPConfigService


@pytest.mark.asyncio
async def test_connection_with_config_empty():
    result = await MCPConfigService.test_connection_with_config({})
    assert result["status"] == "error"
    assert "at least one mcp server" in result["message"].lower()


@pytest.mark.asyncio
async def test_connection_with_config_not_dict():
    # non-empty lists are invalid — empty list is caught by the "no config" check
    result = await MCPConfigService.test_connection_with_config(["not-a-dict"])  # type: ignore
    assert result["status"] == "error"
    assert "json object" in result["message"].lower()


@pytest.mark.asyncio
async def test_connection_missing_url_or_command():
    config = {"server1": {}}
    result = await MCPConfigService.test_connection_with_config(config)
    assert result["status"] == "error"
    assert "missing required" in result["message"].lower()
    assert "url" in result["message"].lower()


@pytest.mark.asyncio
async def test_client_instantiation_failure(monkeypatch):
    # simulate the underlying client raising during construction
    import services.mcp_config_service as svc

    class FakeClient:
        def __init__(self, connections):
            raise ValueError("boom!! invalid syntax")

    monkeypatch.setattr(svc, "MultiServerMCPClient", FakeClient)
    config = {"server1": {"url": "http://example.com"}}
    result = await MCPConfigService.test_connection_with_config(config)
    assert result["status"] == "error"
    assert "invalid mcp configuration" in result["message"].lower()
    assert "boom!!" in result["message"]


@pytest.mark.asyncio
async def test_tool_registration_error_unwrapped(monkeypatch):
    # simulate a failure while getting tools that mentions register/action
    import services.mcp_config_service as svc

    class FakeClient:
        def __init__(self, connections):
            pass

        async def get_tools(self):
            raise Exception("failed to register action 'do_something' because foo")

    monkeypatch.setattr(svc, "MultiServerMCPClient", FakeClient)
    config = {"server1": {"url": "http://example.com"}}
    result = await MCPConfigService.test_connection_with_config(config)
    assert result["status"] == "error"
    assert "failed to register action" in result["message"].lower()


@pytest.mark.asyncio
async def test_exception_group_unwrapped_to_http_401(monkeypatch):
    """ExceptionGroup wrapping httpx.HTTPStatusError should surface the HTTP status."""
    import httpx
    import services.mcp_config_service as svc

    class FakeClient:
        def __init__(self, connections):
            pass

        async def get_tools(self):
            req = httpx.Request("POST", "http://example.com/mcp")
            resp = httpx.Response(401, request=req)
            inner = httpx.HTTPStatusError("401", request=req, response=resp)
            raise ExceptionGroup("unhandled errors in a TaskGroup", [inner])

    monkeypatch.setattr(svc, "MultiServerMCPClient", FakeClient)
    config = {"server1": {"url": "http://example.com"}}
    result = await MCPConfigService.test_connection_with_config(config)
    assert result["status"] == "error"
    assert "401" in result["message"]
    assert "authentication required" in result["message"].lower()


@pytest.mark.asyncio
async def test_exception_group_unwrapped_connect_error(monkeypatch):
    """ExceptionGroup wrapping httpx.ConnectError should give a friendly message."""
    import httpx
    import services.mcp_config_service as svc

    class FakeClient:
        def __init__(self, connections):
            pass

        async def get_tools(self):
            req = httpx.Request("POST", "http://unreachable.example.com/mcp")
            inner = httpx.ConnectError("Connection refused", request=req)
            raise ExceptionGroup("unhandled errors in a TaskGroup", [inner])

    monkeypatch.setattr(svc, "MultiServerMCPClient", FakeClient)
    config = {"server1": {"url": "http://unreachable.example.com"}}
    result = await MCPConfigService.test_connection_with_config(config)
    assert result["status"] == "error"
    assert "unable to reach mcp server" in result["message"].lower()


@pytest.mark.asyncio
async def test_mcp_error_session_terminated(monkeypatch):
    """McpError 'Session terminated' (caused by HTTP 404) should give a clear hint."""
    import services.mcp_config_service as svc
    from mcp.shared.exceptions import McpError
    from mcp.types import ErrorData

    class FakeClient:
        def __init__(self, connections):
            pass

        async def get_tools(self):
            raise McpError(ErrorData(code=32600, message="Session terminated"))

    monkeypatch.setattr(svc, "MultiServerMCPClient", FakeClient)
    config = {"server1": {"url": "http://example.com/wrong-path"}}
    result = await MCPConfigService.test_connection_with_config(config)
    assert result["status"] == "error"
    assert "404" in result["message"] or "endpoint url" in result["message"].lower()
