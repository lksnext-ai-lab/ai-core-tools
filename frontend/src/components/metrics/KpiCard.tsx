import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { formatPercent } from './format';
import CardApp from '../ui/CardApp';

interface Props {
  label: string;
  value: string;
  /** Relative change vs the previous window (0.12 = +12%); null hides the comparison. */
  change?: number | null;
  /** Whether a rise is good (executions) or bad (errors, latency). */
  higherIsBetter?: boolean;
  hint?: string;
}

export function KpiCard({ label, value, change = null, higherIsBetter = true, hint }: Props) {
  return (
    <CardApp variant="white">
      <p className="text-xs font-medium uppercase tracking-wide text-fg dark:text-fg-dark">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-fg dark:text-fg-dark">{value}</p>
      <div className="mt-1 flex min-h-[1rem] items-center gap-2 text-xs">
        {change !== null && <ChangeBadge change={change} higherIsBetter={higherIsBetter} />}
        {hint && <span className="truncate text-fg-secondary dark:text-fg-secondary-dark">{hint}</span>}
      </div>
    </CardApp>
  );
}

function ChangeBadge({ change, higherIsBetter }: { change: number; higherIsBetter: boolean }) {
  const { t } = useTranslation('common');
  const flat = Math.abs(change) < 0.005;
  const good = flat ? null : (change > 0) === higherIsBetter;
  const Icon = flat ? Minus : change > 0 ? ArrowUpRight : ArrowDownRight;
  const tone = good === null
    ? 'text-gray-500 dark:text-gray-400'
    : good ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400';
  return (
    <span className={`inline-flex items-center gap-0.5 font-medium ${tone}`} title={t('metricsDashboard.change.title')}>
      <Icon className="h-3 w-3" aria-hidden />
      {flat ? '0%' : `${change > 0 ? '+' : '−'}${formatPercent(Math.abs(change))}`}
      <span className="sr-only">{t(good === null ? 'metricsDashboard.change.unchanged' : good ? 'metricsDashboard.change.improved' : 'metricsDashboard.change.worsened')} {t('metricsDashboard.change.previousPeriod')}</span>
    </span>
  );
}
