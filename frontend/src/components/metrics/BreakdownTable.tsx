import type { BreakdownDimension, BreakdownItem } from '../../types/metrics';
import { ChartCard } from './TimeseriesCharts';
import { formatCount, formatDateTime, formatMs, formatPercent } from './format';
import { useChartPalette } from './palette';

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
};

interface Props {
  dimensions: BreakdownDimension[];
  active: BreakdownDimension;
  onChange: (d: BreakdownDimension) => void;
  items: BreakdownItem[] | null;
  loading: boolean;
}

export function BreakdownTable({ dimensions, active, onChange, items, loading }: Props) {
  const palette = useChartPalette();
  const maxRuns = Math.max(1, ...(items ?? []).map((i) => i.runs));
  return (
    <ChartCard title="Breakdown" subtitle="Runs include sub-agent calls; tokens are those of each run's own LLM calls">
      <div role="tablist" aria-label="Breakdown dimension" className="mb-3 flex flex-wrap gap-1">
        {dimensions.map((d) => (
          <button
            key={d}
            role="tab"
            type="button"
            aria-selected={d === active}
            onClick={() => onChange(d)}
            className={`rounded-md px-3 py-1 text-sm font-medium ${
              d === active
                ? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
                : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
            }`}
          >
            {DIMENSION_LABELS[d]}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500 dark:border-gray-700 dark:text-gray-400">
              <th className="py-2 pr-4 font-medium">{DIMENSION_LABELS[active].replace(/s$/, '')}</th>
              <th className="py-2 pr-4 font-medium">Runs</th>
              <th className="whitespace-nowrap py-2 pr-4 text-right font-medium">Error rate</th>
              <th className="whitespace-nowrap py-2 pr-4 text-right font-medium">Tokens</th>
              <th className="whitespace-nowrap py-2 pr-4 text-right font-medium">Avg latency</th>
              <th className="whitespace-nowrap py-2 pr-4 text-right font-medium">p95</th>
              <th className="py-2 text-right font-medium">Last run</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {loading && !items && <EmptyRow text="Loading…" />}
            {items && items.length === 0 && <EmptyRow text="No runs in this period." />}
            {items?.map((item) => (
              <tr key={item.key} className="text-gray-700 dark:text-gray-200">
                <td className="max-w-[16rem] py-2 pr-4">
                  <div className="truncate font-medium text-gray-900 dark:text-gray-100" title={item.label}>
                    {active === 'channel' ? CHANNEL_LABELS[item.label] ?? item.label : item.label}
                  </div>
                  {item.secondary_label && (
                    <div className="truncate text-xs text-gray-500 dark:text-gray-400">{item.secondary_label}</div>
                  )}
                </td>
                <td className="py-2 pr-4">
                  <div className="flex items-center gap-2">
                    <span className="w-14 tabular-nums">{formatCount(item.runs)}</span>
                    <span className="hidden h-1.5 w-24 rounded-full bg-gray-100 sm:block dark:bg-gray-700" aria-hidden>
                      <span
                        className="block h-1.5 rounded-full"
                        style={{ width: `${(item.runs / maxRuns) * 100}%`, background: palette.primary }}
                      />
                    </span>
                  </div>
                </td>
                <td className="whitespace-nowrap py-2 pr-4 text-right tabular-nums">{formatPercent(item.error_rate)}</td>
                <td className="whitespace-nowrap py-2 pr-4 text-right tabular-nums">{formatCount(item.total_tokens)}</td>
                <td className="whitespace-nowrap py-2 pr-4 text-right tabular-nums">{formatMs(item.avg_latency_ms)}</td>
                <td className="whitespace-nowrap py-2 pr-4 text-right tabular-nums">{formatMs(item.p95_latency_ms)}</td>
                <td className="whitespace-nowrap py-2 text-right text-gray-500 dark:text-gray-400">{formatDateTime(item.last_seen)}</td>
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
      <td colSpan={7} className="py-6 text-center text-sm text-gray-400 dark:text-gray-500">{text}</td>
    </tr>
  );
}
