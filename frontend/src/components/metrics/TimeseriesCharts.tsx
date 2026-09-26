import type { ComponentProps, ReactNode } from 'react';
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

interface ChartProps {
  data: TimeseriesResponse;
}

export function ChartCard({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="min-w-0 rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <header className="mb-3">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">{title}</h3>
        {subtitle && <p className="text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>}
      </header>
      {children}
    </section>
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
  const palette = useChartPalette();
  return (
    <ChartCard title="Activity" subtitle="Executions, sub-agent calls and failed executions">
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <LineChart data={data.points} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={palette.grid} />
          <XAxis dataKey="ts" tickFormatter={(ts) => formatBucket(ts, data.bucket)} minTickGap={24} {...axisProps(palette)} />
          <YAxis allowDecimals={false} width={44} tickFormatter={formatCount} {...axisProps(palette)} />
          <Tooltip {...tooltipProps(palette, data, formatCount)} />
          <Legend {...legendProps} />
          <Line type="monotone" dataKey="executions" name="Executions" stroke={palette.primary} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
          <Line type="monotone" dataKey="subagent_calls" name="Sub-agent calls" stroke={palette.secondary} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
          <Line type="monotone" dataKey="errors" name="Errors" stroke={palette.critical} strokeWidth={2} strokeDasharray="4 3" dot={false} activeDot={{ r: 4 }} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

/** Input vs output tokens per bucket, stacked (the stack height is the total). */
export function TokensChart({ data }: ChartProps) {
  const palette = useChartPalette();
  return (
    <ChartCard title="Token usage" subtitle="Input and output tokens across all LLM calls">
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <AreaChart data={data.points} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={palette.grid} />
          <XAxis dataKey="ts" tickFormatter={(ts) => formatBucket(ts, data.bucket)} minTickGap={24} {...axisProps(palette)} />
          <YAxis width={44} tickFormatter={formatCount} {...axisProps(palette)} />
          <Tooltip {...tooltipProps(palette, data, formatCount)} />
          <Legend {...legendProps} />
          <Area type="monotone" dataKey="input_tokens" name="Input" stackId="tokens" stroke={palette.primary} strokeWidth={2} fill={palette.primary} fillOpacity={0.25} />
          <Area type="monotone" dataKey="output_tokens" name="Output" stackId="tokens" stroke={palette.secondary} strokeWidth={2} fill={palette.secondary} fillOpacity={0.25} />
        </AreaChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

/** p50 and p95 duration of top-level executions per bucket. */
export function LatencyChart({ data }: ChartProps) {
  const palette = useChartPalette();
  return (
    <ChartCard title="Latency" subtitle="Execution duration, median and 95th percentile">
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
