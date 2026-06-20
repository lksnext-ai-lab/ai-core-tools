/**
 * TypeScript interfaces for the Agent Metrics plugin API responses.
 * Field names match the Python snake_case JSON keys from mattin_metrics/schemas.py.
 */

export type TimeRange = '24h' | '7d' | '30d';

// ── App-level ──────────────────────────────────────────────────────────────

export interface AppSummaryResponse {
  range: string;
  total_executions: number;
  total_executions_incl_subcalls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  error_rate: number;
  avg_latency_ms_p50: number | null;
  avg_latency_ms_p95: number | null;
  active_agents: number;
  active_users: number;
}

export interface ExecutionBucket {
  ts: string;
  root: number;
  sub: number;
  errors: number;
}

export interface AppExecutionsResponse {
  range: string;
  bucket_size: string;
  series: ExecutionBucket[];
}

export interface AgentBreakdown {
  agent_id: number;
  agent_name: string;
  executions: number;
  total_tokens: number;
  error_rate: number;
  avg_latency_ms: number | null;
  last_execution_at: string | null;
}

export interface AppAgentsResponse {
  range: string;
  agents: AgentBreakdown[];
}

export interface ModelBreakdown {
  model_name: string;
  executions: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  error_rate: number;
  avg_latency_ms: number | null;
  last_execution_at: string | null;
}

export interface AppModelsResponse {
  range: string;
  models: ModelBreakdown[];
}

export interface UserBreakdown {
  user_id: number | null;
  user_name: string | null;
  executions: number;
  total_tokens: number;
}

export interface AppUsersResponse {
  range: string;
  users: UserBreakdown[];
  limit: number;
}

// ── Per-agent ──────────────────────────────────────────────────────────────

export interface AgentSummaryResponse {
  range: string;
  executions: number;
  executions_incl_subcalls: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  error_rate: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  latency_p99_ms: number | null;
  active_users: number;
}

export interface AgentExecutionBucket {
  ts: string;
  root: number;
  as_tool: number;
}

export interface AgentExecutionsResponse {
  range: string;
  bucket_size: string;
  series: AgentExecutionBucket[];
}

export interface TokenBucket {
  ts: string;
  input: number;
  output: number;
}

export interface AgentTokensResponse {
  range: string;
  bucket_size: string;
  series: TokenBucket[];
}

export interface ErrorBucket {
  ts: string;
  errors: number;
  total: number;
  rate: number;
}

export interface ErrorByCode {
  error_code: string;
  count: number;
}

export interface AgentErrorsResponse {
  range: string;
  bucket_size: string;
  series: ErrorBucket[];
  by_code: ErrorByCode[];
}

export interface LatencyBucket {
  ts: string;
  p50: number | null;
  p95: number | null;
  p99: number | null;
}

export interface AgentLatencyResponse {
  range: string;
  bucket_size: string;
  series: LatencyBucket[];
}

export interface ToolBreakdown {
  tool_name: string;
  tool_type: string;
  sub_agent_id: number | null;
  calls: number;
  error_rate: number;
  avg_duration_ms: number | null;
}

export interface AgentToolsResponse {
  range: string;
  tools: ToolBreakdown[];
}

export interface AgentUsersResponse {
  range: string;
  users: UserBreakdown[];
  limit: number;
}
