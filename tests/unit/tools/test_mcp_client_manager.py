from types import SimpleNamespace

import pytest

import tools.agentTools as agent_tools
from tools.agentTools import MCPClientManager


class FakeMCPConfig:
    name = "fake-mcp"
    ssl_verify = True

    def __init__(self, connection_config):
        self._connection_config = connection_config

    def to_connection_dict(self):
        return self._connection_config


class FakeMCPClient:
    def __init__(self, connections):
        self.connections = connections


def make_agent(connection_config):
    return SimpleNamespace(
        mcp_associations=[
            SimpleNamespace(mcp=FakeMCPConfig(connection_config)),
        ],
    )


@pytest.mark.asyncio
async def test_mcp_client_preserves_configured_authorization_header(monkeypatch):
    captured = {}

    def fake_client(connections):
        captured["connections"] = connections
        return FakeMCPClient(connections)

    monkeypatch.setattr(agent_tools, "MultiServerMCPClient", fake_client)

    agent = make_agent({
        "tavily": {
            "url": "https://mcp.tavily.com/mcp/",
            "transport": "streamable_http",
            "headers": {"Authorization": "Bearer tvly-configured-key"},
        }
    })

    await MCPClientManager().get_client(
        agent,
        user_context={"oauth": True, "token": "local-mattin-jwt"},
    )

    assert captured["connections"]["tavily"]["headers"]["Authorization"] == (
        "Bearer tvly-configured-key"
    )


@pytest.mark.asyncio
async def test_mcp_client_adds_authorization_when_not_configured(monkeypatch):
    captured = {}

    def fake_client(connections):
        captured["connections"] = connections
        return FakeMCPClient(connections)

    monkeypatch.setattr(agent_tools, "MultiServerMCPClient", fake_client)

    agent = make_agent({
        "internal": {
            "url": "http://mattin-backend:8000/mcp/v1/app/server",
            "transport": "streamable_http",
        }
    })

    await MCPClientManager().get_client(
        agent,
        user_context={"oauth": True, "token": "local-mattin-jwt"},
    )

    assert captured["connections"]["internal"]["headers"]["Authorization"] == (
        "Bearer local-mattin-jwt"
    )


@pytest.mark.asyncio
async def test_mcp_client_preserves_lowercase_authorization_header(monkeypatch):
    captured = {}

    def fake_client(connections):
        captured["connections"] = connections
        return FakeMCPClient(connections)

    monkeypatch.setattr(agent_tools, "MultiServerMCPClient", fake_client)

    agent = make_agent({
        "external": {
            "url": "https://example.com/mcp",
            "headers": {"authorization": "Bearer provider-token"},
        }
    })

    await MCPClientManager().get_client(
        agent,
        user_context={"oauth": True, "token": "local-mattin-jwt"},
    )

    assert captured["connections"]["external"]["headers"] == {
        "authorization": "Bearer provider-token",
    }


@pytest.mark.asyncio
async def test_mcp_client_does_not_add_authorization_when_url_has_api_key(monkeypatch):
    captured = {}

    def fake_client(connections):
        captured["connections"] = connections
        return FakeMCPClient(connections)

    monkeypatch.setattr(agent_tools, "MultiServerMCPClient", fake_client)

    agent = make_agent({
        "tavily": {
            "url": "https://mcp.tavily.com/mcp/?tavilyApiKey=tvly-configured-key",
            "transport": "streamable_http",
        }
    })

    await MCPClientManager().get_client(
        agent,
        user_context={"oauth": True, "token": "local-mattin-jwt"},
    )

    assert captured["connections"]["tavily"]["headers"] == {}
