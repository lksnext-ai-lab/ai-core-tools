import { useTranslation } from 'react-i18next';
import type { BreakdownDimension, BreakdownItem } from '../../types/metrics';
import { Tabs } from '../ui/Tabs';
import { ChartCard } from './TimeseriesCharts';
import { formatCount, formatDateTime, formatMs, formatPercent } from './format';

interface Props {
  dimensions: BreakdownDimension[];
  active: BreakdownDimension;
  onChange: (d: BreakdownDimension) => void;
  items: BreakdownItem[] | null;
  loading: boolean;
}

export function BreakdownTable({ dimensions, active, onChange, items, loading }: Props) {
  const { t } = useTranslation('common');
  const dimensionLabels: Record<BreakdownDimension, string> = {
    app: t('metricsDashboard.dimensions.apps'),
    agent: t('metricsDashboard.dimensions.agents'),
    model: t('metricsDashboard.dimensions.models'),
    provider: t('metricsDashboard.dimensions.providers'),
    channel: t('metricsDashboard.dimensions.channels'),
    user: t('metricsDashboard.dimensions.users'),
  };
  const dimensionTitles: Record<BreakdownDimension, string> = {
    app: t('metricsDashboard.dimensions.app'),
    agent: t('metricsDashboard.dimensions.agent'),
    model: t('metricsDashboard.dimensions.model'),
    provider: t('metricsDashboard.dimensions.provider'),
    channel: t('metricsDashboard.dimensions.channel'),
    user: t('metricsDashboard.dimensions.user'),
  };
  const channelLabels: Record<string, string> = {
    INTERNAL_PLAYGROUND: t('metricsDashboard.channels.playground'),
    PUBLIC_API: t('metricsDashboard.channels.publicApi'),
    MCP: 'MCP',
    AGENT_AS_TOOL: t('metricsDashboard.channels.agentAsTool'),
    SCHEDULED_TASK: t('metricsDashboard.channels.scheduledTask'),
    A2A: 'A2A',
  };
  const maxRuns = Math.max(1, ...(items ?? []).map((i) => i.runs));
  return (
    <ChartCard title={t('metricsDashboard.breakdown.title')} subtitle={t('metricsDashboard.breakdown.description')}>
      <Tabs
        tabs={dimensions.map((dimension) => ({ id: dimension, label: dimensionLabels[dimension] }))}
        activeTab={active}
        onChange={(dimension) => onChange(dimension as BreakdownDimension)}
        className="mb-3"
      />
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-line text-sm dark:divide-line-dark">
          <thead className="bg-tableCab dark:bg-tableCab-dark">
            <tr>
              <th className="px-6 py-3 text-left text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">{dimensionTitles[active]}</th>
              <th className="px-6 py-3 text-left text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">{t('metricsDashboard.table.runs')}</th>
              <th className="whitespace-nowrap px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">{t('metricsDashboard.table.errorRate')}</th>
              <th className="whitespace-nowrap px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">{t('metricsDashboard.table.tokens')}</th>
              <th className="whitespace-nowrap px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">{t('metricsDashboard.table.averageLatency')}</th>
              <th className="whitespace-nowrap px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">p95</th>
              <th className="px-6 py-3 text-right text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark">{t('metricsDashboard.table.lastRun')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {loading && !items && <EmptyRow text={t('metricsDashboard.loading')} />}
            {items && items.length === 0 && <EmptyRow text={t('metricsDashboard.breakdown.noRuns')} />}
            {items?.map((item) => (
              <tr key={item.key} className="text-fg-secondary dark:text-fg-secondary-dark">
                <td className="max-w-[16rem] py-2 pr-4 text-fg dark:text-fg-dark">
                  <div className="truncate font-medium" title={item.label}>
                    {active === 'channel' ? channelLabels[item.label] ?? item.label : item.label}
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
