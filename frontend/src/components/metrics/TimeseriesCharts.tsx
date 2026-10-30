import type { ComponentProps, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TimeseriesResponse } from '../../types/metrics';
import { formatBucket, formatCount, formatMs } from './format';
import { useChartPalette, type ChartPalette } from './palette';
import CardApp from '../ui/CardApp';

interface ChartProps {
  data: TimeseriesResponse;
}

export function ChartCard({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <CardApp className="min-w-0">
      <header className="mb-3">
        <h3 className="text-sm font-semibold text-fg dark:text-fg-dark">{title}</h3>
        {subtitle && <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark">{subtitle}</p>}
      </header>
      {children}
    </CardApp>
  );
}

function axisProps(palette: ChartPalette) {
  return {
    tick: { fontSize: 11, fill: palette.axis },
    tickLine: false,
    axisLine: { stroke: palette.grid },
  };
}

function tooltipProps(
  palette: ChartPalette,
  data: TimeseriesResponse,
  format: (v: number) => string,
): ComponentProps<typeof Tooltip> {
  return {
    cursor: { stroke: palette.axis, strokeWidth: 1, strokeDasharray: '3 3' },
    labelFormatter: (ts) => formatBucket(String(ts), data.bucket, true),
    formatter: (value, name) => [typeof value === 'number' ? format(value) : String(value ?? ''), String(name)],
    contentStyle: {
      background: palette.surface,
      border: `1px solid ${palette.grid}`,
      borderRadius: 8,
      fontSize: 12,
      color: palette.axis,
    },
  };
}

const legendProps = { iconType: 'plainline' as const, wrapperStyle: { fontSize: 12 } };

const CHART_HEIGHT = 220;

/** Executions, sub-agent calls and errors per bucket (counts share one axis). */
export function ActivityChart({ data }: ChartProps) {
  const { t } = useTranslation('common');
  const palette = useChartPalette();
  return (
    <ChartCard title={t('metricsDashboard.charts.activity')} subtitle={t('metricsDashboard.charts.activityDescription')}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <LineChart data={data.points} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={palette.grid} />
          <XAxis dataKey="ts" tickFormatter={(ts) => formatBucket(ts, data.bucket)} minTickGap={24} {...axisProps(palette)} />
          <YAxis allowDecimals={false} width={44} tickFormatter={formatCount} {...axisProps(palette)} />
          <Tooltip {...tooltipProps(palette, data, formatCount)} />
          <Legend {...legendProps} />
          <Line type="monotone" dataKey="executions" name={t('metricsDashboard.kpi.executions')} stroke={palette.primary} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
          <Line type="monotone" dataKey="subagent_calls" name={t('metricsDashboard.charts.subAgentCalls')} stroke={palette.secondary} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
          <Line type="monotone" dataKey="errors" name={t('metricsDashboard.charts.errors')} stroke={palette.critical} strokeWidth={2} strokeDasharray="4 3" dot={false} activeDot={{ r: 4 }} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

/** Input vs output tokens per bucket, stacked (the stack height is the total). */
export function TokensChart({ data }: ChartProps) {
  const { t } = useTranslation('common');
  const palette = useChartPalette();
  return (
    <ChartCard title={t('metricsDashboard.charts.tokenUsage')} subtitle={t('metricsDashboard.charts.tokenUsageDescription')}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <AreaChart data={data.points} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={palette.grid} />
          <XAxis dataKey="ts" tickFormatter={(ts) => formatBucket(ts, data.bucket)} minTickGap={24} {...axisProps(palette)} />
          <YAxis width={44} tickFormatter={formatCount} {...axisProps(palette)} />
          <Tooltip {...tooltipProps(palette, data, formatCount)} />
          <Legend {...legendProps} />
          <Area type="monotone" dataKey="input_tokens" name={t('metricsDashboard.charts.input')} stackId="tokens" stroke={palette.primary} strokeWidth={2} fill={palette.primary} fillOpacity={0.25} />
          <Area type="monotone" dataKey="output_tokens" name={t('metricsDashboard.charts.output')} stackId="tokens" stroke={palette.secondary} strokeWidth={2} fill={palette.secondary} fillOpacity={0.25} />
        </AreaChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

/** p50 and p95 duration of top-level executions per bucket. */
export function LatencyChart({ data }: ChartProps) {
  const { t } = useTranslation('common');
  const palette = useChartPalette();
  return (
    <ChartCard title={t('metricsDashboard.charts.latency')} subtitle={t('metricsDashboard.charts.latencyDescription')}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <LineChart data={data.points} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={palette.grid} />
          <XAxis dataKey="ts" tickFormatter={(ts) => formatBucket(ts, data.bucket)} minTickGap={24} {...axisProps(palette)} />
          <YAxis width={52} tickFormatter={(v) => formatMs(v)} {...axisProps(palette)} />
          <Tooltip {...tooltipProps(palette, data, (v) => formatMs(v))} />
          <Legend {...legendProps} />
          <Line type="monotone" dataKey="latency_p50_ms" name="p50" stroke={palette.primary} strokeWidth={2} dot={false} activeDot={{ r: 4 }} connectNulls />
          <Line type="monotone" dataKey="latency_p95_ms" name="p95" stroke={palette.secondary} strokeWidth={2} dot={false} activeDot={{ r: 4 }} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
