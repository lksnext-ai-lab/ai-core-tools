import { useTranslation } from 'react-i18next';
import type { ToolStats } from '../../types/metrics';
import { ChartCard } from './TimeseriesCharts';
import { formatCount, formatMs, formatPercent } from './format';
import Table, { type TableColumn } from '../ui/Table';
import { Badge } from '../ui/Badge';

export function ToolsTable({ tools }: { tools: ToolStats[] | null }) {
  const { t } = useTranslation('common');
  const typeLabels: Record<ToolStats['tool_type'], string> = {
    AGENT: t('metricsDashboard.tools.types.subAgent'),
    MCP: 'MCP',
    RETRIEVER: t('metricsDashboard.tools.types.knowledgeBase'),
    BUILTIN: t('metricsDashboard.tools.types.builtIn'),
  };
  const columns: TableColumn<ToolStats>[] = [
    {
      header: t('metricsDashboard.tools.tool'),
      className: 'max-w-[16rem] py-2 pr-4',
      render: (tool) => (
        <span className="block truncate font-mono text-xs text-fg dark:text-fg-dark" title={tool.tool_name}>
          {tool.tool_name}
        </span>
      ),
    },
    {
      header: t('metricsDashboard.tools.type'),
      className: 'py-2 pr-4',
      render: (tool) => <Badge label={typeLabels[tool.tool_type] ?? tool.tool_type} variant="default" />,
    },
    {
      header: t('metricsDashboard.tools.calls'),
      headerClassName: 'text-right',
      className: 'whitespace-nowrap py-2 pr-4 text-right tabular-nums text-xs text-fg-secondary dark:text-fg-secondary-dark',
      render: (tool) => formatCount(tool.calls),
    },
    {
      header: t('metricsDashboard.table.errorRate'),
      headerClassName: 'whitespace-nowrap text-right',
      className: 'whitespace-nowrap py-2 pr-4 text-right tabular-nums text-xs text-fg-secondary dark:text-fg-secondary-dark',
      render: (tool) => formatPercent(tool.error_rate),
    },
    {
      header: t('metricsDashboard.tools.average'),
      headerClassName: 'text-right',
      className: 'whitespace-nowrap py-2 pr-4 text-right tabular-nums text-xs text-fg-secondary dark:text-fg-secondary-dark',
      render: (tool) => formatMs(tool.avg_duration_ms),
    },
    {
      header: 'p95',
      headerClassName: 'text-right',
      className: 'whitespace-nowrap py-2 text-right tabular-nums text-xs text-fg-secondary dark:text-fg-secondary-dark',
      render: (tool) => formatMs(tool.p95_duration_ms),
    },
  ];

  return (
    <ChartCard title={t('metricsDashboard.tools.title')} subtitle={t('metricsDashboard.tools.description')}>
      <Table
        columns={columns}
        data={tools ?? []}
        keyExtractor={(tool) => `${tool.tool_type}:${tool.tool_name}`}
        emptyMessage={tools === null ? t('metricsDashboard.loading') : t('metricsDashboard.tools.noCalls')}
        emptyIcon={tools === null ? null : undefined}
      />
    </ChartCard>
  );
}
