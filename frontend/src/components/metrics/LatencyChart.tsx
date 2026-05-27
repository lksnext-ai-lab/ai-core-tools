import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { LatencyBucket } from '../../types/metrics';

interface Props {
  series: LatencyBucket[];
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

export function LatencyChart({ series }: Props) {
  if (!series || series.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-xl border border-gray-200 bg-white text-sm text-gray-400">
        No latency data available for this period.
      </div>
    );
  }

  const data = series.map((b) => ({
    ts: formatTs(b.ts),
    p50: b.p50,
    p95: b.p95,
    p99: b.p99,
  }));

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-gray-700">Latency (ms)</h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="ts" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          <Line
            type="monotone"
            dataKey="p50"
            name="P50"
            stroke="#22c55e"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="p95"
            name="P95"
            stroke="#f59e0b"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="p99"
            name="P99"
            stroke="#ef4444"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
