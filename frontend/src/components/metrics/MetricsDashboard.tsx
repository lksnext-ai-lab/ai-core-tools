import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
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
import { Skeleton } from '../ui/Skeleton';
import Alert from '../ui/Alert';
import Title from '../ui/Title';

interface Props {
  api: MetricsScopeApi;
  dimensions: BreakdownDimension[];
  title?: string;
  description?: string;
  /** System view: show app names and the active-apps KPI. */
  systemScope?: boolean;
}

export function MetricsDashboard({ api, dimensions, title, description, systemScope = false }: Props) {
  const { t } = useTranslation('common');
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
        if (!cancelled) setLoadError(err instanceof Error ? err.message : t('metricsDashboard.loadFailed'));
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
      { label: t('metricsDashboard.kpi.executions'), value: formatCount(c.executions), change: relativeChange(c.executions, p.executions),
        hint: c.subagent_calls ? t('metricsDashboard.kpi.subAgentCalls', { count: c.subagent_calls, formattedCount: formatCount(c.subagent_calls) }) : undefined },
      { label: t('metricsDashboard.kpi.errorRate'), value: formatPercent(c.error_rate), change: relativeChange(c.error_rate, p.error_rate),
        higherIsBetter: false, hint: c.timeouts ? t('metricsDashboard.kpi.timeouts', { count: c.timeouts, formattedCount: formatCount(c.timeouts) }) : t('metricsDashboard.kpi.failed', { count: c.errors, formattedCount: formatCount(c.errors) }) },
      { label: t('metricsDashboard.kpi.latencyP95'), value: formatMs(c.latency_p95_ms), change: relativeChange(c.latency_p95_ms, p.latency_p95_ms),
        higherIsBetter: false, hint: t('metricsDashboard.kpi.latencyMedianHint', { value: formatMs(c.latency_p50_ms) }) },
      { label: t('metricsDashboard.kpi.timeToFirstToken'), value: formatMs(c.ttft_p50_ms), change: relativeChange(c.ttft_p50_ms, p.ttft_p50_ms),
        higherIsBetter: false, hint: t('metricsDashboard.kpi.streamingOnly') },
      { label: t('metricsDashboard.kpi.totalTokens'), value: formatCount(c.total_tokens), change: relativeChange(c.total_tokens, p.total_tokens),
        hint: t('metricsDashboard.kpi.inputOutputTokens', { input: formatCount(c.input_tokens), output: formatCount(c.output_tokens) }) },
      { label: t('metricsDashboard.kpi.tokensPerExecution'), value: c.avg_tokens_per_execution === null ? '—' : formatCount(Math.round(c.avg_tokens_per_execution)),
        change: relativeChange(c.avg_tokens_per_execution, p.avg_tokens_per_execution), higherIsBetter: false,
        hint: t('metricsDashboard.kpi.llmCalls', { count: c.llm_calls, formattedCount: formatCount(c.llm_calls) }) },
      { label: t('metricsDashboard.kpi.toolCalls'), value: formatCount(c.tool_calls), change: relativeChange(c.tool_calls, p.tool_calls),
        hint: c.tool_errors ? t('metricsDashboard.kpi.failed', { count: c.tool_errors, formattedCount: formatCount(c.tool_errors) }) : undefined },
      systemScope
        ? { label: t('metricsDashboard.kpi.activeApps'), value: formatCount(c.active_apps), change: relativeChange(c.active_apps, p.active_apps),
            hint: t('metricsDashboard.kpi.activeAppsHint', { agents: formatCount(c.active_agents), users: formatCount(c.active_users) }) }
        : { label: t('metricsDashboard.kpi.activeUsers'), value: formatCount(c.active_users), change: relativeChange(c.active_users, p.active_users),
            hint: t('metricsDashboard.kpi.activeAgents', { count: c.active_agents, formattedCount: formatCount(c.active_agents) }) },
    ];
  }, [summary, systemScope, t]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          {title ? (
            <Title
              variant={systemScope ? 'titPrincipal' : 'titSecundario'}
              titulo={title}
              subtitulo={description}
            />
          ) : (
            <>
              {title && <h1 className="text-2xl font-bold text-fg dark:text-fg-dark">{title}</h1>}
              {description && <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{description}</p>}
            </>
          )}
        </div>
        <MetricRangeSelector value={range} onChange={setRange} />
      </div>

      {loadError && <Alert type="error" message={loadError} />}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {kpis
          ? kpis.map((k) => <KpiCard key={k.label} {...k} />)
          : Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} shape="block" className="h-[104px]" />
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
