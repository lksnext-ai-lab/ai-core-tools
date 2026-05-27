import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Lock, Mail } from 'lucide-react';
import { useCapability } from '../contexts/CapabilitiesContext';
import { metricsApi } from '../services/metrics';
import type {
  TimeRange,
  AppSummaryResponse,
  AppExecutionsResponse,
  AppAgentsResponse,
  AppModelsResponse,
  AppUsersResponse,
} from '../types/metrics';
import { MetricRangeSelector } from '../components/metrics/MetricRangeSelector';
import { KpiCard } from '../components/metrics/KpiCard';
import { ExecutionsLineChart } from '../components/metrics/ExecutionsLineChart';
import { TopUsersTable } from '../components/metrics/TopUsersTable';

// ── Inline upsell (shown when capability is absent) ───────────────────────

function MetricsUpsell() {
  return (
    <div className="max-w-lg mx-auto mt-16 rounded-xl border border-amber-200 bg-amber-50 p-8 text-center">
      <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-amber-100 border border-amber-300 mb-4">
        <Lock className="w-6 h-6 text-amber-500" />
      </div>
      <h2 className="text-lg font-bold text-gray-900 mb-2">Agent Metrics — Enterprise Edition</h2>
      <p className="text-gray-500 text-sm mb-6">
        Token usage, latency, error and tool-usage dashboards at App and Agent level
        are part of the Mattin AI Enterprise Edition.
      </p>
      <a
        href="mailto:info@lksnext.com?subject=Mattin AI Enterprise Edition — Agent Metrics"
        className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
      >
        <Mail className="w-4 h-4" />
        Contact us to purchase
      </a>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────

function AppMetricsPage() {
  const { appId } = useParams<{ appId: string }>();
  const metricsEnabled = useCapability('metrics');

  const [range, setRange] = useState<TimeRange>('7d');
  const [summary, setSummary] = useState<AppSummaryResponse | null>(null);
  const [executions, setExecutions] = useState<AppExecutionsResponse | null>(null);
  const [agents, setAgents] = useState<AppAgentsResponse | null>(null);
  const [models, setModels] = useState<AppModelsResponse | null>(null);
  const [users, setUsers] = useState<AppUsersResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!metricsEnabled || !appId) return;

    const id = Number(appId);
    setLoading(true);
    setError(null);

    Promise.all([
      metricsApi.appSummary(id, range),
      metricsApi.appExecutions(id, range),
      metricsApi.appAgents(id, range),
      metricsApi.appModels(id, range),
      metricsApi.appUsers(id, range),
    ])
      .then(([s, e, a, m, u]) => {
        setSummary(s);
        setExecutions(e);
        setAgents(a);
        setModels(m);
        setUsers(u);
      })
      .catch((err) => {
        console.error('Failed to load metrics:', err);
        setError('Failed to load metrics data. Please try again.');
      })
      .finally(() => setLoading(false));
  }, [appId, range, metricsEnabled]);

  if (!metricsEnabled) {
    return <MetricsUpsell />;
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Metrics</h1>
        <MetricRangeSelector value={range} onChange={setRange} />
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading && !summary && (
        <div className="text-sm text-gray-400">Loading metrics…</div>
      )}

      {/* KPI row */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiCard
            label="Total Executions"
            value={summary.total_executions.toLocaleString()}
          />
          <KpiCard
            label="Error Rate"
            value={`${(summary.error_rate * 100).toFixed(1)}%`}
            trend={summary.error_rate > 0.1 ? 'down' : 'neutral'}
          />
          <KpiCard
            label="P50 Latency"
            value={
              summary.avg_latency_ms_p50 != null
                ? `${Math.round(summary.avg_latency_ms_p50)}ms`
                : '—'
            }
          />
          <KpiCard
            label="Active Agents"
            value={summary.active_agents}
          />
        </div>
      )}

      {/* Executions chart */}
      {executions && (
        <ExecutionsLineChart series={executions.series} />
      )}

      {/* Agents breakdown table */}
      {agents && agents.agents.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold text-gray-700">Agents</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                <th className="pb-2 font-medium">Name</th>
                <th className="pb-2 font-medium text-right">Executions</th>
                <th className="pb-2 font-medium text-right">Total Tokens</th>
                <th className="pb-2 font-medium text-right">Error Rate</th>
                <th className="pb-2 font-medium text-right">Avg Latency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {agents.agents.map((a) => (
                <tr key={a.agent_id} className="hover:bg-gray-50">
                  <td className="py-2 font-medium text-gray-800">{a.agent_name}</td>
                  <td className="py-2 text-right tabular-nums text-gray-700">
                    {a.executions.toLocaleString()}
                  </td>
                  <td className="py-2 text-right tabular-nums text-gray-700">
                    {a.total_tokens.toLocaleString()}
                  </td>
                  <td className="py-2 text-right tabular-nums text-gray-700">
                    {(a.error_rate * 100).toFixed(1)}%
                  </td>
                  <td className="py-2 text-right tabular-nums text-gray-700">
                    {a.avg_latency_ms != null ? `${Math.round(a.avg_latency_ms)}ms` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Models breakdown table */}
      {models && models.models.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold text-gray-700">By Model</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                <th className="pb-2 font-medium">Model</th>
                <th className="pb-2 font-medium text-right">Executions</th>
                <th className="pb-2 font-medium text-right">Input Tokens</th>
                <th className="pb-2 font-medium text-right">Output Tokens</th>
                <th className="pb-2 font-medium text-right">Total Tokens</th>
                <th className="pb-2 font-medium text-right">Error Rate</th>
                <th className="pb-2 font-medium text-right">Avg Latency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {models.models.map((m) => (
                <tr key={m.model_name} className="hover:bg-gray-50">
                  <td className="py-2 font-medium text-gray-800 font-mono text-xs">{m.model_name}</td>
                  <td className="py-2 text-right tabular-nums text-gray-700">
                    {m.executions.toLocaleString()}
                  </td>
                  <td className="py-2 text-right tabular-nums text-gray-700">
                    {m.input_tokens.toLocaleString()}
                  </td>
                  <td className="py-2 text-right tabular-nums text-gray-700">
                    {m.output_tokens.toLocaleString()}
                  </td>
                  <td className="py-2 text-right tabular-nums text-gray-700 font-medium">
                    {m.total_tokens.toLocaleString()}
                  </td>
                  <td className="py-2 text-right tabular-nums text-gray-700">
                    {(m.error_rate * 100).toFixed(1)}%
                  </td>
                  <td className="py-2 text-right tabular-nums text-gray-700">
                    {m.avg_latency_ms != null ? `${Math.round(m.avg_latency_ms)}ms` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Top users */}
      {users && <TopUsersTable users={users.users} />}
    </div>
  );
}

export default AppMetricsPage;
