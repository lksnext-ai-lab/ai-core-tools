import type { TimeRange } from '../../types/metrics';

interface Props {
  value: TimeRange;
  onChange: (v: TimeRange) => void;
}

const RANGES: { label: string; value: TimeRange }[] = [
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
  { label: '30d', value: '30d' },
];

export function MetricRangeSelector({ value, onChange }: Props) {
  return (
    <div className="flex items-center gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1">
      {RANGES.map((r) => (
        <button
          key={r.value}
          onClick={() => onChange(r.value)}
          className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
            value === r.value
              ? 'bg-blue-600 text-white shadow-sm'
              : 'text-gray-600 hover:bg-gray-200'
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}
