import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { ErrorBucket } from '../../types/metrics';

interface Props {
  series: ErrorBucket[];
}

function formatTs(ts: string): string {
  try {
    const d = new Date(ts);
    const h = d.getUTCHours().toString().padStart(2, '0');
    const m = d.getUTCMinutes().toString().padStart(2, '0');
    if (h === '00' && m === '00') {
      return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
    }
    return `${h}:${m}`;
  } catch {
    return ts;
  }
}

export function ErrorsChart({ series }: Props) {
  if (!series || series.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-xl border border-gray-200 bg-white text-sm text-gray-400">
        No error data available for this period.
      </div>
    );
  }

  const data = series.map((b) => ({
    ts: formatTs(b.ts),
    errors: b.errors,
    rate: parseFloat((b.rate * 100).toFixed(1)),
  }));

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-gray-700">Errors</h3>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="ts" tick={{ fontSize: 11 }} />
          <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} unit="%" />
          <Tooltip />
          <Legend />
          <Bar yAxisId="left" dataKey="errors" name="Error count" fill="#fca5a5" />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="rate"
            name="Error rate %"
            stroke="#ef4444"
            strokeWidth={2}
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
