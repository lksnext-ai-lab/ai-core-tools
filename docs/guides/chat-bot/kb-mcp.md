# MCP Integration

## What is MCP?

**MCP** (Model Context Protocol) is an open standard for connecting AI agents to external tools and data sources. Mattin AI supports MCP in two directions:

| Direction | Description |
|-----------|-------------|
| **MCP Client** | Your agents connect to external MCP servers and use their tools |
| **MCP Server** | Your agents are exposed as MCP tools to external clients (e.g. Claude Desktop, Cursor) |

## MCP Client — Using External Tools

You can connect your agents to any MCP-compatible tool server. This gives agents access to external capabilities such as database queries, file systems, APIs, or custom business tools.

### Adding an MCP Config to your App

1. Open your App and go to **MCP Configs**.
2. Click **New MCP Config**.
3. Enter the server connection details (URL, transport type, and any required authentication).
4. Save.

### Attaching an MCP Config to an Agent

1. Open the agent configuration.
2. Go to the **MCP** section.
3. Select one or more MCP Configs.
4. Save.

The agent will now have access to the tools provided by those MCP servers during conversations.

## MCP Server — Exposing Your Agents

You can expose one or more of your agents as MCP tools, allowing external AI clients (Claude Desktop, Cursor, custom apps) to call them.

### Creating an MCP Server

1. Open your App and go to **MCP Servers**.
2. Click **New MCP Server**.
3. Give it a name.
4. Select the **agents** you want to expose as tools.
5. Save.

The platform will provide a connection URL and an API key for external clients to connect to this MCP Server.

### Connecting from an External Client

Use the connection details provided by the MCP Server configuration. For example, in Claude Desktop's `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "my-mattin-agents": {
      "url": "https://your-platform/mcp/v1/...",
      "headers": {
        "X-API-KEY": "your-api-key"
      }
    }
  }
}
```

## API Keys for MCP Access

External MCP clients and the public API authenticate using **API Keys**.

To create an API Key:
1. Open your App and go to **API Keys**.
2. Click **New API Key**.
3. Copy the key — it is shown only once.
4. Use it as the `X-API-KEY` header in API or MCP requests.

## Notes

- MCP tools are only available when the agent is actively processing a message — they are not background processes.
- Tool results are included in the agent's context and may be visible in the conversation.
- Connecting to external MCP servers requires the server to be accessible from the platform's network.
