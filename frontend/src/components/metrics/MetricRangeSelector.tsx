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
  return (
    <div role="group" aria-label="Time range" className="flex items-center gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1 dark:border-gray-700 dark:bg-gray-800">
      {RANGES.map((r) => (
        <button
          key={r.value}
          type="button"
          aria-pressed={value === r.value}
          onClick={() => onChange(r.value)}
          className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
            value === r.value
              ? 'bg-blue-600 text-white shadow-sm'
              : 'text-gray-600 hover:bg-gray-200 dark:text-gray-300 dark:hover:bg-gray-700'
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}
