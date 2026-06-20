import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { TokenBucket } from '../../types/metrics';

interface Props {
  series: TokenBucket[];
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

export function TokenStackedAreaChart({ series }: Props) {
  if (!series || series.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-xl border border-gray-200 bg-white text-sm text-gray-400">
        No token data available for this period.
      </div>
    );
  }

  const data = series.map((b) => ({
    ts: formatTs(b.ts),
    input: b.input,
    output: b.output,
  }));

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-gray-700">Token Usage</h3>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="ts" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          <Area
            type="monotone"
            dataKey="input"
            name="Input tokens"
            stackId="1"
            stroke="#3b82f6"
            fill="#bfdbfe"
          />
          <Area
            type="monotone"
            dataKey="output"
            name="Output tokens"
            stackId="1"
            stroke="#6366f1"
            fill="#c7d2fe"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
