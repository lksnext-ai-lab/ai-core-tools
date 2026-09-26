interface Props {
  label: string;
  value: string | number;
  subLine?: string;
  trend?: 'up' | 'down' | 'neutral';
}

const trendColors = {
  up: 'text-green-600',
  down: 'text-red-500',
  neutral: 'text-gray-500',
};

export function KpiCard({ label, value, subLine, trend }: Props) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold text-gray-900 ${trend ? trendColors[trend] : ''}`}>
        {value}
      </p>
      {subLine && (
        <p className="mt-0.5 text-xs text-gray-400">{subLine}</p>
      )}
    </div>
  );
}
