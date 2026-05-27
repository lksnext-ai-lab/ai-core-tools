import { useState, useEffect } from 'react';
import { Lock, Mail } from 'lucide-react';
import { useCapability } from '../../contexts/CapabilitiesContext';
import { metricsApi } from '../../services/metrics';
import type {
  TimeRange,
  AgentSummaryResponse,
  AgentExecutionsResponse,
  AgentTokensResponse,
  AgentErrorsResponse,
  AgentLatencyResponse,
  AgentToolsResponse,
  AgentUsersResponse,
} from '../../types/metrics';
import { MetricRangeSelector } from './MetricRangeSelector';
import { KpiCard } from './KpiCard';
import { ExecutionsLineChart } from './ExecutionsLineChart';
import { TokenStackedAreaChart } from './TokenStackedAreaChart';
import { LatencyChart } from './LatencyChart';
import { ErrorsChart } from './ErrorsChart';
import { ToolsBarChart } from './ToolsBarChart';
import { TopUsersTable } from './TopUsersTable';

interface AgentMetricsTabProps {
  appId: number;
  agentId: number;
}

function MetricsUpsell() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 p-6 text-center">
      <Lock className="w-6 h-6 text-amber-500" />
      <p className="text-sm text-gray-700 font-medium">
        Agent Metrics is an Enterprise Edition feature.
      </p>
      <a
        href="mailto:info@lksnext.com?subject=Mattin AI Enterprise Edition — Agent Metrics"
        className="inline-flex items-center gap-2 px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 transition-colors"
      >
        <Mail className="w-3 h-3" />
        Contact us
      </a>
    </div>
  );
}

export function AgentMetricsTab({ appId, agentId }: AgentMetricsTabProps) {
  const metricsEnabled = useCapability('metrics');

  const [range, setRange] = useState<TimeRange>('7d');
  const [summary, setSummary] = useState<AgentSummaryResponse | null>(null);
  const [executions, setExecutions] = useState<AgentExecutionsResponse | null>(null);
  const [tokens, setTokens] = useState<AgentTokensResponse | null>(null);
  const [errors, setErrors] = useState<AgentErrorsResponse | null>(null);
  const [latency, setLatency] = useState<AgentLatencyResponse | null>(null);
  const [tools, setTools] = useState<AgentToolsResponse | null>(null);
  const [users, setUsers] = useState<AgentUsersResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!metricsEnabled) return;

    setLoading(true);
    setLoadError(null);

    Promise.all([
      metricsApi.agentSummary(appId, agentId, range),
      metricsApi.agentExecutions(appId, agentId, range),
      metricsApi.agentTokens(appId, agentId, range),
      metricsApi.agentErrors(appId, agentId, range),
      metricsApi.agentLatency(appId, agentId, range),
      metricsApi.agentTools(appId, agentId, range),
      metricsApi.agentUsers(appId, agentId, range),
    ])
      .then(([s, e, t, err, l, tl, u]) => {
        setSummary(s);
        setExecutions(e);
        setTokens(t);
        setErrors(err);
        setLatency(l);
        setTools(tl);
        setUsers(u);
      })
      .catch((err) => {
        console.error('Failed to load agent metrics:', err);
        setLoadError('Failed to load metrics. Please try again.');
      })
      .finally(() => setLoading(false));
  }, [appId, agentId, range, metricsEnabled]);

  if (!metricsEnabled) {
    return <MetricsUpsell />;
  }

  return (
    <div className="space-y-6">
      {/* Range selector */}
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-gray-800">Agent Metrics</h3>
        <MetricRangeSelector value={range} onChange={setRange} />
      </div>

      {loadError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {loadError}
        </div>
      )}

      {loading && !summary && (
        <div className="text-sm text-gray-400">Loading metrics…</div>
      )}

      {/* KPI row */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          <KpiCard
            label="Executions"
            value={summary.executions.toLocaleString()}
          />
          <KpiCard
            label="As Tool"
            value={(summary.executions_incl_subcalls - summary.executions).toLocaleString()}
          />
          <KpiCard
            label="Error Rate"
            value={`${(summary.error_rate * 100).toFixed(1)}%`}
            trend={summary.error_rate > 0.1 ? 'down' : 'neutral'}
          />
          <KpiCard
            label="P50 Latency"
            value={summary.latency_p50_ms != null ? `${Math.round(summary.latency_p50_ms)}ms` : '—'}
          />
          <KpiCard
            label="P95 Latency"
            value={summary.latency_p95_ms != null ? `${Math.round(summary.latency_p95_ms)}ms` : '—'}
          />
          <KpiCard
            label="Total Tokens"
            value={summary.total_tokens.toLocaleString()}
          />
        </div>
      )}

      {/* Charts row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {executions && (
          <ExecutionsLineChart series={executions.series} agentView />
        )}
        {tokens && (
          <TokenStackedAreaChart series={tokens.series} />
        )}
      </div>

      {/* Charts row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {latency && <LatencyChart series={latency.series} />}
        {errors && <ErrorsChart series={errors.series} />}
      </div>

      {/* Tools breakdown */}
      {tools && <ToolsBarChart tools={tools.tools} />}

      {/* Top users */}
      {users && <TopUsersTable users={users.users} />}
    </div>
  );
}
