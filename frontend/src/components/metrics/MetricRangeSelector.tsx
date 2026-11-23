import { useTranslation } from 'react-i18next';
import type { TimeRange } from '../../types/metrics';

const RANGES: { label: string; value: TimeRange }[] = [
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
  { label: '30d', value: '30d' },
  { label: '90d', value: '90d' },
];

interface Props {
  value: TimeRange;
  onChange: (v: TimeRange) => void;
}

export function MetricRangeSelector({ value, onChange }: Props) {
  const { t } = useTranslation('common');
  return (
    <div role="group" aria-label={t('metricsDashboard.timeRange')} className="flex items-center gap-1 rounded-lg bg-white dark:bg-surface-dark border border-line dark:border-btCard-border-dark">
      {RANGES.map((r) => (
        <button
          key={r.value}
          type="button"
          aria-pressed={value === r.value}
          onClick={() => onChange(r.value)}
          className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
            value === r.value
              ? 'bg-fg dark:bg-fg-dark text-ink-on dark:text-ink-on-dark shadow-sm'
              : 'text-fg dark:text-fg-dark'
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}
