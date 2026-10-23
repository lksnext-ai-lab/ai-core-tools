import type { BreakdownDimension, BreakdownItem } from '../../types/metrics';
import { Tabs } from '../ui/Tabs';
import { ChartCard } from './TimeseriesCharts';
import { formatCount, formatDateTime, formatMs, formatPercent } from './format';

export const DIMENSION_LABELS: Record<BreakdownDimension, string> = {
  app: 'Apps',
  agent: 'Agents',
  model: 'Models',
  provider: 'Providers',
  channel: 'Channels',
  user: 'Users',
};

const CHANNEL_LABELS: Record<string, string> = {
  INTERNAL_PLAYGROUND: 'Playground',
  PUBLIC_API: 'Public API',
  MCP: 'MCP',
  AGENT_AS_TOOL: 'Agent as tool',
  SCHEDULED_TASK: 'Scheduled task',
  A2A: 'A2A',
};

interface Props {
  dimensions: BreakdownDimension[];
  active: BreakdownDimension;
  onChange: (d: BreakdownDimension) => void;
  items: BreakdownItem[] | null;
  loading: boolean;
}

export function BreakdownTable({ dimensions, active, onChange, items, loading }: Props) {
  const maxRuns = Math.max(1, ...(items ?? []).map((i) => i.runs));
  return (
    <ChartCard title="Breakdown" subtitle="Runs include sub-agent calls; tokens are those of each run's own LLM calls">
      <Tabs
        tabs={dimensions.map((dimension) => ({ id: dimension, label: DIMENSION_LABELS[dimension] }))}
        activeTab={active}
        onChange={(dimension) => onChange(dimension as BreakdownDimension)}
        className="mb-3"
      />
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-line text-sm dark:divide-line-dark">
          <thead className="bg-tableCab dark:bg-tableCab-dark">
            <tr>
              <th className="px-6 py-3 text-left text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">{DIMENSION_LABELS[active].replace(/s$/, '')}</th>
              <th className="px-6 py-3 text-left text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">Runs</th>
              <th className="whitespace-nowrap px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">Error rate</th>
              <th className="whitespace-nowrap px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">Tokens</th>
              <th className="whitespace-nowrap px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">Avg latency</th>
              <th className="whitespace-nowrap px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">p95</th>
              <th className="px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">Last run</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {loading && !items && <EmptyRow text="Loading…" />}
            {items && items.length === 0 && <EmptyRow text="No runs in this period." />}
            {items?.map((item) => (
              <tr key={item.key} className="text-fg-secondary dark:text-fg-secondary-dark">
                <td className="max-w-[16rem] py-2 pr-4 text-fg dark:text-fg-dark">
                  <div className="truncate font-medium" title={item.label}>
                    {active === 'channel' ? CHANNEL_LABELS[item.label] ?? item.label : item.label}
                  </div>
                  {item.secondary_label && (
                    <div className="truncate text-xs">{item.secondary_label}</div>
                  )}
                </td>
                <td className="py-2 pr-4">
                  <div className="flex items-center gap-2">
                    <span className="w-14 tabular-nums">{formatCount(item.runs)}</span>
                    <span className="hidden h-1.5 w-24 rounded-full bg-gray-100 sm:block dark:bg-gray-700" aria-hidden>
                      <span
                        className="block h-1.5 rounded-full bg-fg dark:bg-fg-dark"
                        style={{ width: `${(item.runs / maxRuns) * 100}%` }}
                      />
                    </span>
                  </div>
                </td>
                <td className="whitespace-nowrap py-2 pr-4 text-right tabular-nums">{formatPercent(item.error_rate)}</td>
                <td className="whitespace-nowrap py-2 pr-4 text-right tabular-nums">{formatCount(item.total_tokens)}</td>
                <td className="whitespace-nowrap py-2 pr-4 text-right tabular-nums">{formatMs(item.avg_latency_ms)}</td>
                <td className="whitespace-nowrap py-2 pr-4 text-right tabular-nums">{formatMs(item.p95_latency_ms)}</td>
                <td className="whitespace-nowrap py-2 text-right">{formatDateTime(item.last_seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ChartCard>
  );
}

export function EmptyRow({ text }: { text: string }) {
  return (
    <tr>
      <td colSpan={7} className="py-6 text-center text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{text}</td>
    </tr>
  );
}
