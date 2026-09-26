# Agent Metrics

> Part of [Mattin AI Documentation](../README.md)

Every agent execution is recorded as an event — duration, status, token usage, LLM and tool calls, caller channel, model — and aggregated into dashboards at three levels: the whole platform, an app, and a single agent. Per-execution traces (prompts, individual steps) stay in [LangSmith](../../backend/tools/langsmith_config.py); these dashboards answer "how much, how fast, how reliable".

---

## Dashboards

| View | Where | Who |
|------|-------|-----|
| **Platform** | Sidebar → Administration → **Agent Metrics** (`/admin/metrics`) | Platform admins (omniadmins or `platform_role = admin`) |
| **App** | App sidebar → **Metrics** (`/apps/:appId/metrics`) | App `administrator` and above |
| **Agent** | Agent form → **Metrics** tab | App `editor` and above |

Each view has a 24h / 7d / 30d / 90d range and shows:

- **KPIs** with the change against the previous period of the same length: executions, error rate, latency p95 (and p50), time to first token (streaming), total tokens, tokens per execution, tool calls, active apps/users.
- **Activity**, **token usage** (input vs output) and **latency** (p50/p95) over time. Empty periods show as zero.
- **Breakdown** by app, agent, model, provider, channel (playground, public API, MCP, agent-as-tool) or user — whichever apply to the view.
- **Tools**: calls, error rate and avg/p95 duration per tool, with its type (knowledge base, MCP, sub-agent, built-in).
- **Errors** grouped by error type, plus the latest failed executions.

There are no costs in money: token prices vary by contract, cache and region, so the dashboards report tokens.

## How counting works

- **Executions** are top-level runs. A run of an agent used as a tool by another agent is a **sub-agent call**, linked to its parent execution and shown separately.
- **Tokens and LLM calls** of a run are those of the agent's *own* LLM calls. A sub-agent's calls are recorded on the sub-agent's run, never on its parent, so summing all runs gives the true total without double counting.
- **Error rate** is failed executions / executions. Timeouts and cancelled runs count as failures.

## How it is recorded

`AgentMetricsCollector` (`backend/services/agent_metrics_collector.py`) is a LangChain callback handler attached to each run. Callbacks propagate into tools, so it sees every LLM and tool call, and keeps only the agent's direct ones: anything that runs under an `AGENT` tool belongs to the sub-agent.

- **LLM calls**: token usage summed over all calls of the turn (tool loops included); the model name reported by the provider.
- **Tool calls**: name, type, duration, status and error. The type comes from tool metadata set when the agent's tools are built (`tools/agentTools.py`): retrievers are `RETRIEVER`, MCP tools `MCP`, agents used as tools `AGENT`, everything else `BUILTIN`.
- **Time to first token**: measured by the streaming service when the first token is sent.

`services/agent_metrics_recorder.py` builds the event and writes it in a background task on its own DB session. Recording is best-effort: it never raises and never delays the response.

Instrumented paths: non-streaming chat (`AgentExecutionService`), streaming chat (`AgentStreamingService`) and agent-as-tool calls (`IACTTool`). OCR agents are not instrumented.

## API

All endpoints are `GET` and take `?range=24h|7d|30d|90d` (default `7d`). The three scopes share the same endpoints and response shapes:

| Scope | Prefix |
|-------|--------|
| Platform | `/internal/admin/metrics` |
| App | `/internal/apps/{app_id}/metrics` |
| Agent | `/internal/apps/{app_id}/agents/{agent_id}/metrics` |

| Endpoint | Returns |
|----------|---------|
| `/summary` | KPIs for the range and for the previous range |
| `/timeseries` | Gap-filled points (1h buckets for 24h, 6h for 7d, 1d for 30d/90d) |
| `/breakdown/{dimension}` | Top 50 by runs. Platform: `app`, `agent`, `model`, `provider`, `channel`. App: `agent`, `model`, `provider`, `channel`, `user`. Agent: `model`, `channel`, `user` |
| `/tools` | Top 50 tools by calls |
| `/errors` | Error groups and the 20 latest failures |

## Architecture

```
backend/
├── models/agent_execution_event.py, models/agent_tool_call.py
├── services/agent_metrics_collector.py   # callback handler (capture)
├── services/agent_metrics_recorder.py    # payload + background write
├── services/metrics_query_service.py     # scoped aggregate queries
├── schemas/metrics_schemas.py
└── routers/internal/metrics.py           # the three scopes
frontend/src/
├── components/metrics/MetricsDashboard.tsx  # shared by the three views
├── components/metrics/*                     # KPI tiles, charts (recharts), tables
├── pages/AppMetricsPage.tsx, pages/admin/AdminMetricsPage.tsx
└── services/metrics.ts                      # metricsApi.system() / .app(id) / .agent(appId, id)
```

Migrations: `metrics002` creates the tables (keeping them when the former `mattin-metrics` plugin already did), `metrics003` adds `llm_calls`, `time_to_first_token_ms`, `provider`, a `started_at` index for platform-wide queries and the `BUILTIN` tool type.
