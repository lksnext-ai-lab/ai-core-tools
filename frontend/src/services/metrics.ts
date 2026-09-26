import { apiService } from './api';
import type {
  BreakdownDimension,
  BreakdownResponse,
  ErrorsResponse,
  SummaryResponse,
  TimeRange,
  TimeseriesResponse,
  ToolsResponse,
} from '../types/metrics';

/** The same metrics endpoints, bound to one scope (system, app or agent). */
export interface MetricsScopeApi {
  summary: (range: TimeRange) => Promise<SummaryResponse>;
  timeseries: (range: TimeRange) => Promise<TimeseriesResponse>;
  breakdown: (dimension: BreakdownDimension, range: TimeRange) => Promise<BreakdownResponse>;
  tools: (range: TimeRange) => Promise<ToolsResponse>;
  errors: (range: TimeRange) => Promise<ErrorsResponse>;
}

function scopeApi(base: string): MetricsScopeApi {
  const get = <T,>(path: string, range: TimeRange): Promise<T> =>
    apiService.request(`${base}/${path}?range=${range}`);
  return {
    summary: (range) => get('summary', range),
    timeseries: (range) => get('timeseries', range),
    breakdown: (dimension, range) => get(`breakdown/${dimension}`, range),
    tools: (range) => get('tools', range),
    errors: (range) => get('errors', range),
  };
}

export const metricsApi = {
  system: (): MetricsScopeApi => scopeApi('/internal/admin/metrics'),
  app: (appId: number): MetricsScopeApi => scopeApi(`/internal/apps/${appId}/metrics`),
  agent: (appId: number, agentId: number): MetricsScopeApi =>
    scopeApi(`/internal/apps/${appId}/agents/${agentId}/metrics`),
};
