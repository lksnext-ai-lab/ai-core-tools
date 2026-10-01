// Agent metrics dashboards — mirrors backend/schemas/metrics_schemas.py.
// "executions" are top-level runs; sub-agent calls are counted separately.
// Token and LLM-call totals include every run (each records only its own calls).

export type TimeRange = '24h' | '7d' | '30d' | '90d';
export type BreakdownDimension = 'app' | 'agent' | 'model' | 'provider' | 'channel' | 'user';

export interface SummaryStats {
  executions: number;
  subagent_calls: number;
  errors: number;
  timeouts: number;
  error_rate: number;
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  avg_tokens_per_execution: number | null;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  ttft_p50_ms: number | null;
  ttft_p95_ms: number | null;
  tool_calls: number;
  tool_errors: number;
  active_apps: number;
  active_agents: number;
  active_users: number;
}

export interface SummaryResponse {
  range: TimeRange;
  current: SummaryStats;
  previous: SummaryStats;
}

export interface TimeseriesPoint {
  ts: string;
  executions: number;
  subagent_calls: number;
  errors: number;
  input_tokens: number;
  output_tokens: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
}

export interface TimeseriesResponse {
  range: TimeRange;
  bucket: '1h' | '6h' | '1d';
  points: TimeseriesPoint[];
}

export interface BreakdownItem {
  key: string;
  label: string;
  secondary_label: string | null;
  runs: number;
  errors: number;
  error_rate: number;
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  last_seen: string | null;
}

export interface BreakdownResponse {
  range: TimeRange;
  dimension: BreakdownDimension;
  items: BreakdownItem[];
}

export interface ToolStats {
  tool_name: string;
  tool_type: 'AGENT' | 'MCP' | 'RETRIEVER' | 'BUILTIN';
  calls: number;
  errors: number;
  error_rate: number;
  avg_duration_ms: number | null;
  p95_duration_ms: number | null;
}

export interface ToolsResponse {
  range: TimeRange;
  tools: ToolStats[];
}

export interface ErrorGroup {
  error_code: string;
  count: number;
  last_seen: string;
  sample_message: string | null;
}

export interface RecentError {
  started_at: string;
  app_id: number;
  app_name: string | null;
  agent_id: number;
  agent_name: string | null;
  caller_type: string;
  error_code: string | null;
  error_message: string | null;
}

export interface ErrorsResponse {
  range: TimeRange;
  groups: ErrorGroup[];
  recent: RecentError[];
}
