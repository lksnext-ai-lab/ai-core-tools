import { useEffect, useMemo, useState } from 'react';
import type {
  BreakdownDimension,
  BreakdownItem,
  ErrorsResponse,
  SummaryResponse,
  TimeRange,
  TimeseriesResponse,
  ToolStats,
} from '../../types/metrics';
import type { MetricsScopeApi } from '../../services/metrics';
import { BreakdownTable } from './BreakdownTable';
import { ErrorsPanel } from './ErrorsPanel';
import { KpiCard } from './KpiCard';
import { MetricRangeSelector } from './MetricRangeSelector';
import { ActivityChart, LatencyChart, TokensChart } from './TimeseriesCharts';
import { ToolsTable } from './ToolsTable';
import { formatCount, formatMs, formatPercent, relativeChange } from './format';

interface Props {
  api: MetricsScopeApi;
  dimensions: BreakdownDimension[];
  title?: string;
  description?: string;
  /** System view: show app names and the active-apps KPI. */
  systemScope?: boolean;
}

export function MetricsDashboard({ api, dimensions, title, description, systemScope = false }: Props) {
  const [range, setRange] = useState<TimeRange>('7d');
  const [dimension, setDimension] = useState<BreakdownDimension>(dimensions[0]);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [series, setSeries] = useState<TimeseriesResponse | null>(null);
  const [tools, setTools] = useState<ToolStats[] | null>(null);
  const [errors, setErrors] = useState<ErrorsResponse | null>(null);
  const [breakdown, setBreakdown] = useState<BreakdownItem[] | null>(null);
  const [breakdownLoading, setBreakdownLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    Promise.all([api.summary(range), api.timeseries(range), api.tools(range), api.errors(range)])
      .then(([s, t, tl, e]) => {
        if (cancelled) return;
        setSummary(s);
        setSeries(t);
        setTools(tl.tools);
        setErrors(e);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Failed to load metrics.');
      });
    return () => { cancelled = true; };
  }, [api, range]);

  useEffect(() => {
    let cancelled = false;
    setBreakdownLoading(true);
    api.breakdown(dimension, range)
      .then((b) => { if (!cancelled) setBreakdown(b.items); })
      .catch(() => { if (!cancelled) setBreakdown([]); })
      .finally(() => { if (!cancelled) setBreakdownLoading(false); });
    return () => { cancelled = true; };
  }, [api, dimension, range]);

  const kpis = useMemo(() => {
    if (!summary) return null;
    const { current: c, previous: p } = summary;
    return [
      { label: 'Executions', value: formatCount(c.executions), change: relativeChange(c.executions, p.executions),
        hint: c.subagent_calls ? `+${formatCount(c.subagent_calls)} sub-agent calls` : undefined },
      { label: 'Error rate', value: formatPercent(c.error_rate), change: relativeChange(c.error_rate, p.error_rate),
        higherIsBetter: false, hint: c.timeouts ? `${formatCount(c.timeouts)} timeouts` : `${formatCount(c.errors)} failed` },
      { label: 'Latency p95', value: formatMs(c.latency_p95_ms), change: relativeChange(c.latency_p95_ms, p.latency_p95_ms),
        higherIsBetter: false, hint: `p50 ${formatMs(c.latency_p50_ms)}` },
      { label: 'Time to first token', value: formatMs(c.ttft_p50_ms), change: relativeChange(c.ttft_p50_ms, p.ttft_p50_ms),
        higherIsBetter: false, hint: 'p50, streaming only' },
      { label: 'Total tokens', value: formatCount(c.total_tokens), change: relativeChange(c.total_tokens, p.total_tokens),
        hint: `${formatCount(c.input_tokens)} in · ${formatCount(c.output_tokens)} out` },
      { label: 'Tokens / execution', value: c.avg_tokens_per_execution === null ? '—' : formatCount(Math.round(c.avg_tokens_per_execution)),
        change: relativeChange(c.avg_tokens_per_execution, p.avg_tokens_per_execution), higherIsBetter: false,
        hint: `${formatCount(c.llm_calls)} LLM calls` },
      { label: 'Tool calls', value: formatCount(c.tool_calls), change: relativeChange(c.tool_calls, p.tool_calls),
        hint: c.tool_errors ? `${formatCount(c.tool_errors)} failed` : undefined },
      systemScope
        ? { label: 'Active apps', value: formatCount(c.active_apps), change: relativeChange(c.active_apps, p.active_apps),
            hint: `${formatCount(c.active_agents)} agents · ${formatCount(c.active_users)} users` }
        : { label: 'Active users', value: formatCount(c.active_users), change: relativeChange(c.active_users, p.active_users),
            hint: `${formatCount(c.active_agents)} agents` },
    ];
  }, [summary, systemScope]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          {title && <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{title}</h1>}
          {description && <p className="text-sm text-gray-600 dark:text-gray-400">{description}</p>}
        </div>
        <MetricRangeSelector value={range} onChange={setRange} />
      </div>

      {loadError && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {loadError}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {kpis
          ? kpis.map((k) => <KpiCard key={k.label} {...k} />)
          : Array.from({ length: 8 }, (_, i) => (
              <div key={i} className="h-[104px] animate-pulse rounded-xl border border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800" />
            ))}
      </div>

      {series && (
        <>
          <ActivityChart data={series} />
          <div className="grid gap-6 lg:grid-cols-2">
            <TokensChart data={series} />
            <LatencyChart data={series} />
          </div>
        </>
      )}

      <BreakdownTable
        dimensions={dimensions}
        active={dimension}
        onChange={setDimension}
        items={breakdown}
        loading={breakdownLoading}
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <ToolsTable tools={tools} />
        <ErrorsPanel errors={errors} showApp={systemScope} />
      </div>
    </div>
  );
}
