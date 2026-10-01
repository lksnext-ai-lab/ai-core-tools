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
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500 dark:border-gray-700 dark:text-gray-400">
              <th className="py-2 pr-4 font-medium">Tool</th>
              <th className="py-2 pr-4 font-medium">Type</th>
              <th className="py-2 pr-4 text-right font-medium">Calls</th>
              <th className="whitespace-nowrap py-2 pr-4 text-right font-medium">Error rate</th>
              <th className="py-2 pr-4 text-right font-medium">Avg</th>
              <th className="py-2 text-right font-medium">p95</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {!tools && <EmptyRow text="Loading…" />}
            {tools && tools.length === 0 && <EmptyRow text="No tool calls in this period." />}
            {tools?.map((t) => (
              <tr key={`${t.tool_type}:${t.tool_name}`} className="text-gray-700 dark:text-gray-200">
                <td className="max-w-[16rem] truncate py-2 pr-4 font-mono text-xs text-gray-900 dark:text-gray-100" title={t.tool_name}>{t.tool_name}</td>
                <td className="py-2 pr-4">
                  <span className="whitespace-nowrap rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-200">
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
