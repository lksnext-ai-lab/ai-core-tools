# App Export and Import

> Part of [Mattin AI Documentation](../README.md)

## Overview

Mattin AI supports exporting a complete app configuration to a JSON file and importing it into a new app. The export includes app configuration and component definitions but excludes heavy data and secrets.

This guide documents the internal API endpoints and the export file contents used by the export/import workflow.

## Export

**Endpoint**: `POST /internal/apps/{app_id}/export`

**Auth**: session cookie (internal API)

**Min role**: viewer

**Response**: JSON matching the `AppExportFileSchema` structure.

**Export includes**:

- AI services (API keys removed)
- Embedding services (API keys removed)
- Output parsers
- MCP configs (secrets removed)
- Silos
- Repositories (structure only)
- Domains (structure and URLs only)
- Agents (configuration only, no conversations)
- App metadata (name, rate limit, LangSmith enabled)

**Export excludes**:

- User accounts and permissions
- Conversation history
- Vector data
- Files and attachments
- Usage statistics

**Example**:

```http
POST /internal/apps/42/export
Cookie: session=...
```

```json
{
  "metadata": {
    "export_version": "1.0.0",
    "export_date": "2026-03-03T12:00:00Z",
    "exported_by": "user@example.com",
    "source_app_id": 42
  },
  "app": {
    "name": "My Workspace",
    "agent_rate_limit": 0,
    "enable_langsmith": false
  },
  "ai_services": [
    {
      "name": "GPT-4 Service",
      "api_key": null,
      "provider": "openai",
      "model_name": "gpt-4-turbo",
      "endpoint": null,
      "description": "GPT-4",
      "api_version": null
    }
  ],
  "embedding_services": [],
  "output_parsers": [],
  "mcp_configs": [],
  "silos": [],
  "repositories": [],
  "domains": [],
  "agents": []
}
```

## Preview Import

**Endpoint**: `POST /internal/apps/preview-import`

**Auth**: session cookie (internal API)

**Min role**: user

**Request**: multipart form data with a single `file` field containing the export JSON.

**Response**: `AppImportPreviewSchema` with component inventory, dependencies, and warnings.

**Example**:

```http
POST /internal/apps/preview-import
Cookie: session=...
Content-Type: multipart/form-data

file=@app-export.json
```

## Import

**Endpoint**: `POST /internal/apps/import`

**Auth**: session cookie (internal API)

**Min role**: user

**Request**: multipart form data with a `file` field and optional parameters.

**Query parameters**:

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `conflict_mode` | string | `fail` | How to handle name conflicts: `fail`, `rename`, `override` |
| `new_name` | string | null | Custom app name to use with rename mode |

**Form fields**:

| Field | Type | Description |
| --- | --- | --- |
| `file` | file | Export JSON file (required) |
| `component_selection_json` | string | JSON mapping of component types to a list of names to import |
| `api_keys_json` | string | JSON mapping of AI/embedding service names to API keys |

**Important behavior**:

- Import always creates a new app from the export metadata.
- If `conflict_mode=fail` and an app with the same name exists, the API returns `409`.
- `component_selection_json` is optional; if omitted, all components are imported.

**Component selection keys**:

- `ai_service`
- `embedding_service`
- `output_parser`
- `mcp_config`
- `silo`
- `repository`
- `domain`
- `agent`

**Example**:

```http
POST /internal/apps/import?conflict_mode=rename&new_name=Imported%20Workspace
Cookie: session=...
Content-Type: multipart/form-data

file=@app-export.json
component_selection_json={"ai_service":["GPT-4 Service"],"agent":["Support Bot"]}
api_keys_json={"GPT-4 Service":"sk-..."}
```

## Security and Data Handling Notes

- Export files use **name-based references** instead of database IDs.
- All API keys are removed from exports. Supply them on import using `api_keys_json`.
- MCP configs are sanitized to remove auth tokens.
- Vectors, file contents, and conversations are not exported.

## Demo App

A curated demo workspace JSON is available at `scripts/demo-app.json`. It can be imported to instantly set up a fully configured demo workspace showcasing all major platform features.

### What's included

| Entity Type | Count | Highlights |
|-------------|-------|------------|
| AI Services | 4 | OpenAI, Anthropic, Ollama (local), Azure OpenAI |
| Embedding Services | 2 | OpenAI, Ollama (local) |
| Output Parsers | 2 | Structured Summary, Q&A with Confidence |
| MCP Configs | 1 | External tool server (placeholder) |
| Silos | 1 | PGVector-backed knowledge base |
| Repositories | 1 | File-based document store (empty — upload files after import) |
| Domains | 1 | Web scraping source (placeholder URL) |
| Agents | 8 | FAQ, RAG KB, conversational (memory), structured output, tool sub-agent, orchestrator, OCR (dual-LLM), Azure |

### Import the demo

Use the import endpoint or the UI import dialog:

```http
POST /internal/apps/import?conflict_mode=rename
Cookie: session=...
Content-Type: multipart/form-data

file=@scripts/demo-app.json
api_keys_json={"Demo OpenAI GPT-5.4":"sk-...","Demo Anthropic Claude":"sk-ant-..."}
```

Or from the frontend: **Apps → Import App → select `demo-app.json` → provide API keys → Import**.

### Post-import manual steps

Some features are not supported by the import schema and must be configured manually after import:

| Feature | Action |
|---------|--------|
| **Skills** | Create skills via the UI and link them to agents |
| **`is_tool` flag** | Edit the "Demo Intent Classifier (Tool)" agent and enable `is_tool` |
| **MCP Server** | Create an MCP server and attach the desired agents |
| **API keys** | Supply real provider API keys (via `api_keys_json` during import or edit each service after import) |

## See Also

- [Internal API](../api/internal-api.md)
