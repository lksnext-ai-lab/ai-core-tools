import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import { formatPercent } from './format';

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
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-100">{value}</p>
      <div className="mt-1 flex min-h-[1rem] items-center gap-2 text-xs">
        {change !== null && <ChangeBadge change={change} higherIsBetter={higherIsBetter} />}
        {hint && <span className="truncate text-gray-400 dark:text-gray-500">{hint}</span>}
      </div>
    </div>
  );
}

function ChangeBadge({ change, higherIsBetter }: { change: number; higherIsBetter: boolean }) {
  const flat = Math.abs(change) < 0.005;
  const good = flat ? null : (change > 0) === higherIsBetter;
  const Icon = flat ? Minus : change > 0 ? ArrowUpRight : ArrowDownRight;
  const tone = good === null
    ? 'text-gray-500 dark:text-gray-400'
    : good ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400';
  return (
    <span className={`inline-flex items-center gap-0.5 font-medium ${tone}`} title="Change vs the previous period">
      <Icon className="h-3 w-3" aria-hidden />
      {flat ? '0%' : `${change > 0 ? '+' : '−'}${formatPercent(Math.abs(change))}`}
      <span className="sr-only">{good === null ? 'unchanged' : good ? 'improved' : 'worsened'} vs previous period</span>
    </span>
  );
}
