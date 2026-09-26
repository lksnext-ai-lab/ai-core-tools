# Agent Metrics

> Part of [Mattin AI Documentation](../README.md)

Every agent execution is recorded as an event (duration, status, tokens, caller, model) so each app gets a usage dashboard and each agent a **Metrics** tab.

---

## What is recorded

One `agent_execution_event` row per agent run, written in the background after the run finishes. Recording is best-effort: a failed write is logged and never affects the agent's response.

| Field | Source |
|-------|--------|
| `status` | `SUCCESS`, `ERROR` (including cancelled runs) or `TIMEOUT` |
| `duration_ms` | Wall-clock time of the LLM invocation |
| `input_tokens` / `output_tokens` / `total_tokens` | `usage_metadata` of the last model message of the turn |
| `caller_type` | `INTERNAL_PLAYGROUND`, `PUBLIC_API`, `MCP` or `AGENT_AS_TOOL` |
| `parent_execution_id` | For `AGENT_AS_TOOL` runs, the event of the agent that called the sub-agent |
| `user_id`, `api_key_id`, `conversation_id` | Only when the caller provides a numeric id |
| `model_name`, `ai_service_id` | The agent's AI service |

Instrumented paths:

- `AgentExecutionService._execute_agent_async` — non-streaming chat (internal, public API, MCP)
- `AgentStreamingService.stream_agent_chat` — streaming chat
- `IACTTool` — each sub-agent call made by an agent used as a tool

OCR agents are not instrumented.

## Dashboard

- **App dashboard** — sidebar **Metrics** (`/apps/:appId/metrics`). Requires the `administrator` app role.
- **Agent tab** — **Metrics** tab in the agent form. Requires the `editor` app role.

Both offer 24h, 7d and 30d ranges.

## API Endpoints

All endpoints are `GET` and take `?range=24h|7d|30d` (default `7d`).

| Path | Role |
|------|------|
| `/internal/apps/{app_id}/metrics/{summary,executions,agents,models,users}` | administrator |
| `/internal/apps/{app_id}/agents/{agent_id}/metrics/{summary,executions,tokens,errors,latency,tools,users}` | editor |

## Architecture

```
backend/
├── models/agent_execution_event.py, models/agent_tool_call.py
├── services/agent_metrics_recorder.py   # build payload + background write
├── services/metrics_query_service.py    # dashboard queries
├── schemas/metrics_schemas.py
└── routers/internal/metrics.py
frontend/src/
├── pages/AppMetricsPage.tsx
├── components/metrics/                   # AgentMetricsTab + charts (recharts)
└── services/metrics.ts
```

Migration `metrics002` creates the tables. Databases that previously ran the standalone `mattin-metrics` plugin already have them: the migration keeps the existing data, drops the plugin's `alembic_version_metrics` table and removes its `parent_execution_id` foreign key (a sub-agent's event is written before its parent's, so that key rejected every sub-agent event).
