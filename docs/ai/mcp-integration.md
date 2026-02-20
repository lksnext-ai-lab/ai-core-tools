# MCP Integration

> Part of [Mattin AI Documentation](../README.md)

## Overview

**Model Context Protocol (MCP)** is an open protocol that standardizes how applications provide context to LLMs. Mattin AI supports MCP, allowing agents to connect to **MCP servers** that expose tools and resources.

**Key features**:
- **Multi-server support**: Agents can connect to multiple MCP servers simultaneously
- **Authentication**: Support for authenticated MCP servers via MCP auth utils
- **Tool integration**: MCP tools automatically available to agents
- **Resource access**: Access MCP resources (files, data sources, APIs)
- **Server management**: Create, start, stop, and manage MCP servers
- **Dedicated router**: `/mcp/v1/*` endpoints for MCP server communication

**Use cases**:
- Access external data sources (databases, APIs, file systems)
- Integrate with third-party services (GitHub, Slack, Jira)
- Extend agent capabilities without custom tool development

## MCP Servers

### MCP Server Model

```python
class MCPServer(Base):
    __tablename__ = 'mcp_servers'
    
    server_id = Column(Integer, primary_key=True)
    app_id = Column(Integer, ForeignKey('App.app_id'))
    name = Column(String(255))
    command = Column(String(500))  # Server command (e.g., 'npx', 'python')
    args = Column(JSON)             # Command arguments
    env = Column(JSON)              # Environment variables
    status = Column(String(45))     # 'running', 'stopped'
```

**Example MCPServer configuration** (GitHub MCP server):

```json
{
  "name": "GitHub MCP",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-github"],
  "env": {
    "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..."
  }
}
```

### Configuration

MCP servers can be configured via Internal API:

```bash
POST /internal/mcp_servers
Content-Type: application/json

{
  "name": "GitHub MCP",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-github"],
  "env": {
    "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..."
  }
}
```

### Management Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/internal/mcp_servers` | GET | List all MCP servers |
| `/internal/mcp_servers` | POST | Create new MCP server |
| `/internal/mcp_servers/{id}` | GET | Get MCP server details |
| `/internal/mcp_servers/{id}` | PUT | Update MCP server |
| `/internal/mcp_servers/{id}` | DELETE | Delete MCP server |
| `/internal/mcp_servers/{id}/start` | POST | Start MCP server |
| `/internal/mcp_servers/{id}/stop` | POST | Stop MCP server |

## MCP Handler

The MCP handler module (`backend/mcp_handler/`) provides server lifecycle management and authentication:

### server_handler.py

Manages MCP server processes:

```python
class MCPServerHandler:
    def start_server(server_config: MCPServer) -> Process:
        """Start an MCP server process"""
        
    def stop_server(server_id: int):
        """Stop a running MCP server"""
        
    def get_server_status(server_id: int) -> str:
        """Get current server status (running/stopped)"""
```

**Lifecycle**:
1. **Create server config** in database
2. **Start process** via `subprocess.Popen(command, args, env)`
3. **Monitor status** (process running → status: 'running')
4. **Stop process** when no longer needed

### auth.py

MCP authentication utilities:

```python
def prepare_mcp_headers(auth_token: str) -> Dict[str, str]:
    """Prepare authentication headers for MCP servers"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "X-User-Token": auth_token
    }

def get_user_token_from_context(user_context: Dict) -> Optional[str]:
    """Extract user authentication token from context"""
    return user_context.get("auth_token") or user_context.get("api_key")
```

**Authentication flow**:

1. **User context** passed to agent execution
2. **Extract auth token** from user context
3. **Prepare MCP headers** with token
4. **Add headers** to MCP server connection config
5. **MCP server validates** token on each request

## MCP Configuration

### MCP Config Model

Legacy model for MCP configuration (being deprecated in favor of MCPServer):

```python
class MCPConfig(Base):
    __tablename__ = 'MCPConfig'
    
    config_id = Column(Integer, primary_key=True)
    app_id = Column(Integer, ForeignKey('App.app_id'))
    name = Column(String(255))
    protocol_version = Column(String(45))
    config_data = Column(JSON)  # Connection configuration
```

### Per-App MCP Settings

Each app can have its own MCP servers:

```python
class App(Base):
    mcp_servers = relationship('MCPServer', back_populates='app')
    mcp_configs = relationship('MCPConfig', back_populates='app')
```

**Isolation**: App A's MCP servers are not accessible to App B (multi-tenant isolation).

### Configuration JSON Structure

For SSE connections:

```json
{
  "github-mcp": {
    "url": "https://mcp-github-server.example.com/sse",
    "headers": {
      "Authorization": "Bearer <token>"
    }
  }
}
```

For stdio connections (process-based):

```json
{
  "filesystem-mcp": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"],
    "env": {
      "LOG_LEVEL": "info"
    }
  }
}
```

## MCP Authentication

### Security Model

**Two-tier authentication**:

1. **Mattin AI → MCP Server**: Mattin AI authenticates to MCP server using configured credentials (API keys, tokens)
2. **User → MCP Server (via Mattin AI)**: User's auth token passed through to MCP server for user-specific access

**Token flow**:

```
User Request (with auth token)
    ↓
Mattin AI Backend
    ↓
Extract user token
    ↓
Prepare MCP headers
    ↓
MCP Client (with auth headers)
    ↓
MCP Server (validates user token)
```

### MCP Auth Utils

Located in `utils/mcp_auth_utils.py`:

```python
def prepare_mcp_headers(auth_token: str) -> Dict[str, str]:
    """Prepare authentication headers for MCP servers."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "X-User-Token": auth_token
    }

def get_user_token_from_context(user_context: Dict) -> Optional[str]:
    """Extract user authentication token from context."""
    return user_context.get("auth_token") or user_context.get("api_key")
```

**Usage in agent execution**:

```python
# In MCPClientManager.get_client()
if user_context:
    auth_token = get_user_token_from_context(user_context)
    if auth_token:
        headers = prepare_mcp_headers(auth_token)
        # Add headers to MCP server connection config
```

## MCP Router

The **MCP Router** (`/mcp/v1/*`) provides dedicated endpoints for MCP server communication:

```python
from routers.mcp import mcp_router

app.include_router(mcp_router, prefix="/mcp/v1", tags=["MCP"])
```

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/mcp/v1/servers` | List available MCP servers |
| `/mcp/v1/servers/{id}/tools` | Get tools from an MCP server |
| `/mcp/v1/servers/{id}/resources` | Get resources from an MCP server |
| `/mcp/v1/callback` | Callback endpoint for MCP server events |

**Use case**: MCP servers can call back to Mattin AI to access resources or trigger agent actions.

### Authentication

MCP router endpoints use **custom protocol-based authentication** (not session or API key auth).

**Authentication header**:

```http
Authorization: Bearer <mcp-server-token>
```

## Agent-Server Association

Agents connect to MCP servers via the **AgentMCP** junction table:

```python
class AgentMCP(Base):
    __tablename__ = 'agent_mcps'
    agent_id = Column(Integer, ForeignKey('Agent.agent_id'))
    config_id = Column(Integer, ForeignKey('MCPConfig.config_id'))
    description = Column(Text)  # What this MCP is used for
```

**Multi-server support**: An agent can be associated with multiple MCP servers, gaining access to all their tools.

**Example**: An agent connected to both GitHub MCP and Filesystem MCP can:
- Create GitHub issues
- Read local files
- All in the same conversation

## Available MCP Servers

Popular MCP servers (from Model Context Protocol ecosystem):

| Server | Package | Tools Provided |
|--------|---------|----------------|
| **GitHub** | `@modelcontextprotocol/server-github` | create_issue, list_repos, get_file, create_pr |
| **Filesystem** | `@modelcontextprotocol/server-filesystem` | read_file, write_file, list_directory, search_files |
| **PostgreSQL** | `@modelcontextprotocol/server-postgres` | query, list_tables, describe_table |
| **Slack** | `@modelcontextprotocol/server-slack` | send_message, list_channels, get_thread |
| **Memory** | `@modelcontextprotocol/server-memory` | store_memory, retrieve_memory, search_memories |

**Installation** (for local MCP servers):

```bash
# Install MCP server globally
npm install -g @modelcontextprotocol/server-github

# Or use npx (no installation needed)
npx -y @modelcontextprotocol/server-github
```

## Best Practices

1. **Secure credentials**: Store MCP server API keys in `env` field, not in public config
2. **Authentication**: Always pass user context for authenticated MCP servers
3. **Error handling**: Handle MCP server errors gracefully (server down, invalid credentials)
4. **Resource management**: MCP clients are created per-request; no manual cleanup needed
5. **Tool selection**: Be selective about which MCP servers an agent connects to (avoid tool overload)
6. **Logging**: Enable MCP debugging during development (`MCP_DEBUG=true`)
7. **Server lifecycle**: Stop MCP servers when not in use to conserve resources

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| **MCP server not starting** | Invalid command or args | Verify command and args in MCPServer config |
| **Authentication errors** | Missing or invalid token | Check user_context and token extraction |
| **Tools not available** | MCP client not initialized | Verify agent has MCP associations |
| **Server crash** | MCP server error | Check MCP server logs, restart server |
| **Connection refused** | Server not running | Start server via `/mcp_servers/{id}/start` |

## See Also

- [Agent System](agent-system.md) — How agents use MCP tools
- [LLM Integration](llm-integration.md) — Agent LLM configuration
- [Backend Architecture](../architecture/backend.md) — MCP router
- [Database Schema](../architecture/database.md) — MCPConfig, MCPServer models
- [Model Context Protocol Docs](https://modelcontextprotocol.io/) — Official MCP documentation
