import type { ToolStats } from '../../types/metrics';
import { EmptyRow } from './BreakdownTable';
import { ChartCard } from './TimeseriesCharts';
import { formatCount, formatMs, formatPercent } from './format';

const TYPE_LABELS: Record<ToolStats['tool_type'], string> = {
  AGENT: 'Sub-agent',
  MCP: 'MCP',
  RETRIEVER: 'Knowledge base',
  BUILTIN: 'Built-in',
};

export function ToolsTable({ tools }: { tools: ToolStats[] | null }) {
  return (
    <ChartCard title="Tools" subtitle="Direct tool calls made by the agents">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-line text-sm dark:divide-line-dark">
          <thead className="bg-tableCab dark:bg-tableCab-dark">
            <tr>
              <th className="px-6 py-3 text-left text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">Tool</th>
              <th className="px-6 py-3 text-left text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">Type</th>
              <th className="px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">Calls</th>
              <th className="whitespace-nowrap px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">Error rate</th>
              <th className="px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">Avg</th>
              <th className="px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">p95</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {!tools && <EmptyRow text="Loading…" />}
            {tools && tools.length === 0 && <EmptyRow text="No tool calls in this period." />}
            {tools?.map((t) => (
              <tr key={`${t.tool_type}:${t.tool_name}`} className="text-fg-secondary dark:text-fg-secondary-dark">
                <td className="max-w-[16rem] truncate py-2 pr-4 font-mono text-xs text-fg dark:text-fg-dark" title={t.tool_name}>{t.tool_name}</td>
                <td className="py-2 pr-4">
                  <span className="whitespace-nowrap rounded-full bg-gray-100 px-2 py-0.5 text-xs text-fg-secondary dark:bg-gray-700 dark:text-fg-secondary-dark">
                    {TYPE_LABELS[t.tool_type] ?? t.tool_type}
                  </span>
                </td>
                <td className="whitespace-nowrap py-2 pr-4 text-right tabular-nums">{formatCount(t.calls)}</td>
                <td className="whitespace-nowrap py-2 pr-4 text-right tabular-nums">{formatPercent(t.error_rate)}</td>
                <td className="whitespace-nowrap py-2 pr-4 text-right tabular-nums">{formatMs(t.avg_duration_ms)}</td>
                <td className="whitespace-nowrap py-2 text-right tabular-nums">{formatMs(t.p95_duration_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ChartCard>
  );
}
